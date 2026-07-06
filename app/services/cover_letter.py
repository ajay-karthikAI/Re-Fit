"""Cover-letter generation, verification, persistence, and rendering."""

from dataclasses import dataclass
import logging
import re
import uuid

import anyio.to_thread
import numpy as np
from rapidfuzz import fuzz
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import CoverLetter, CoverLetterTone, Document, DocumentKind, JobTarget, Profile
from app.models import ResumeVersion
from app.schemas.cover_letter import (
    CoverLetterOutput,
    CoverLetterRequest,
    CoverLetterResult,
    Tone,
)
from app.schemas.jd import JobRequirements
from app.schemas.llm import LLMUsage
from app.schemas.render import RenderRequest, RenderResponse
from app.schemas.resume import StructuredResume
from app.services import storage
from app.services.claims import verify_prose
from app.services.embeddings import embed_texts
from app.services.errors import ConflictError, NotFoundError, ProseVerificationError
from app.services.jd import extract_requirements
from app.services.llm import generate_structured
from app.services.render import (
    render_cover_letter_docx_result,
    render_cover_letter_pdf_result,
)

logger = logging.getLogger(__name__)

MIN_WORDS = 250
MAX_WORDS = 350

SYSTEM_PROMPT = """\
You write factual, grounded cover letters from a deliberately small evidence
pack. The evidence pack is the only source you may use.

Hard constraints:

- Write 250-350 words in 3-4 paragraphs; aim for 285-310 words so the draft
  stays comfortably inside the limit.
- Do not write "To Whom It May Concern". If no hiring manager name is provided,
  use "Dear {company_or_team} team,".
- Do not restate the resume. Connect 2-3 specific candidate experiences to 2-3
  specific job requirements.
- Every factual statement about the candidate must trace to an evidence_ref
  from a resume bullet or matched skill.
- Every factual statement about the company or role must trace to a JD snippet.
- Do not add employers, titles, dates, tools, metrics, outcomes, team sizes,
  company praise, mutual connections, or personal backstory absent from the
  evidence pack.
- Numbers are sacred: use only exact numeric strings from the evidence pack.
  Do not convert 8k to 8000 or 200k to 200,000.
- Do not use meta labels like "The Candidate" or "the candidate"; write in the
  first person.
- Avoid every banned phrase supplied in the user message.
- Tone "standard": clear and professional.
- Tone "direct": shorter, plainer, and no adjectives.
- Tone "warm": one personal-connection sentence is allowed only if it is
  directly evidence-backed.

Return body_markdown and claims_used. Each claims_used item must include the
statement and the exact evidence_ref that supports it.
"""


@dataclass(frozen=True)
class EvidenceBullet:
    ref: str
    text: str
    score: float
    target: str


@dataclass(frozen=True)
class JDSnippet:
    ref: str
    text: str


@dataclass(frozen=True)
class EvidencePack:
    bullets: list[EvidenceBullet]
    matched_skills: list[str]
    jd_snippets: list[JDSnippet]
    must_haves: list[str]
    company_or_team: str
    title: str | None

    @property
    def refs(self) -> set[str]:
        refs = {bullet.ref for bullet in self.bullets}
        refs.update(snippet.ref for snippet in self.jd_snippets)
        refs.update(f"/skills/{index}" for index, _ in enumerate(self.matched_skills))
        return refs


def _json_ref(*parts: object) -> str:
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'+-]+\b", text))


def _sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    return [
        sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", normalized) if sentence.strip()
    ]


def _requirement_targets(requirements: JobRequirements) -> list[tuple[str, float]]:
    targets: dict[str, float] = {}
    for item in requirements.hard_skills:
        stripped = item.term.strip()
        if stripped:
            targets[stripped] = max(targets.get(stripped, 0.0), item.weight)
    for must_have in requirements.must_haves:
        stripped = must_have.strip()
        if stripped:
            targets[stripped] = max(targets.get(stripped, 0.0), 1.0)
    return list(targets.items())


async def _embed(texts: list[str]) -> np.ndarray:
    return await anyio.to_thread.run_sync(embed_texts, texts)


def _all_bullet_refs(resume: StructuredResume) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for i, item in enumerate(resume.experience):
        for j, bullet in enumerate(item.bullets):
            refs.append((_json_ref("experience", i, "bullets", j), bullet))
    for i, project in enumerate(resume.projects):
        for j, bullet in enumerate(project.bullets):
            refs.append((_json_ref("projects", i, "bullets", j), bullet))
    return refs


async def _evidence_bullets(
    resume: StructuredResume, requirements: JobRequirements
) -> list[EvidenceBullet]:
    refs = _all_bullet_refs(resume)
    targets = _requirement_targets(requirements)
    if not refs or not targets:
        return []

    bullet_vectors = await _embed([text for _, text in refs])
    target_vectors = await _embed([term for term, _ in targets])
    similarities = bullet_vectors @ target_vectors.T
    weights = np.asarray([weight for _, weight in targets], dtype=np.float32)
    weighted = similarities * weights

    evidence: list[EvidenceBullet] = []
    for row, (ref, text) in enumerate(refs):
        best_index = int(np.argmax(weighted[row]))
        evidence.append(
            EvidenceBullet(
                ref=ref,
                text=text,
                score=round(float(weighted[row][best_index]), 4),
                target=targets[best_index][0],
            )
        )
    evidence.sort(key=lambda bullet: bullet.score, reverse=True)
    return evidence[: min(6, max(4, len(evidence)))]


def _skill_matches(skill: str, targets: list[str]) -> bool:
    normalized = skill.lower()
    for target in targets:
        target_normalized = target.lower()
        if normalized in target_normalized or target_normalized in normalized:
            return True
        if fuzz.partial_ratio(normalized, target_normalized) >= 90:
            return True
    return False


def _matched_skills(resume: StructuredResume, requirements: JobRequirements) -> list[str]:
    targets = [item.term for item in requirements.hard_skills]
    targets.extend(requirements.must_haves)
    targets.extend(requirements.domain_terms)
    candidates: list[str] = []
    for group in resume.skills:
        candidates.extend(group.items)
    for item in resume.experience:
        candidates.extend(item.technologies)
    for project in resume.projects:
        candidates.extend(project.technologies)

    seen: set[str] = set()
    matched: list[str] = []
    for skill in candidates:
        key = skill.lower()
        if key in seen:
            continue
        seen.add(key)
        if _skill_matches(skill, targets):
            matched.append(skill)
    return matched


def _jd_snippets(raw_jd: str, requirements: JobRequirements) -> list[JDSnippet]:
    snippets: list[str] = []
    for item in requirements.hard_skills + requirements.soft_skills:
        if item.evidence.strip():
            snippets.append(item.evidence.strip())
    snippets.extend(item.strip() for item in requirements.must_haves if item.strip())
    jd_sentences = _sentences(raw_jd)
    for sentence in jd_sentences:
        if any(term.lower() in sentence.lower() for term in requirements.must_haves):
            snippets.append(sentence)

    deduped: list[str] = []
    seen: set[str] = set()
    for snippet in snippets:
        key = snippet.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(snippet)
    return [
        JDSnippet(ref=f"/jd/snippets/{index}", text=text) for index, text in enumerate(deduped[:8])
    ]


def _guess_company_or_team(raw_jd: str) -> str:
    for pattern in [
        r"(?im)^[^\n—-]+\s+[—-]\s+([A-Z][^\n(,;]+)",
        r"(?im)^\s*company\s*:\s*([A-Z][^\n,.;]+)",
        r"(?im)^\s*about\s+([A-Z][A-Za-z0-9& .'-]+)\s*$",
    ]:
        match = re.search(pattern, raw_jd)
        if match and match.group(1).strip().lower() not in {"us", "the role", "the company"}:
            return match.group(1).strip()
    return "hiring"


def _guess_title(raw_jd: str) -> str | None:
    for pattern in [
        r"(?im)^\s*title\s*:\s*([^\n]+)",
        r"(?im)^\s*role\s*:\s*([^\n]+)",
    ]:
        match = re.search(pattern, raw_jd)
        if match:
            return match.group(1).strip()
    return None


async def _build_evidence_pack(
    resume_version: StructuredResume,
    requirements: JobRequirements,
    raw_jd: str,
) -> EvidencePack:
    return EvidencePack(
        bullets=await _evidence_bullets(resume_version, requirements),
        matched_skills=_matched_skills(resume_version, requirements),
        jd_snippets=_jd_snippets(raw_jd, requirements),
        must_haves=requirements.must_haves,
        company_or_team=_guess_company_or_team(raw_jd),
        title=_guess_title(raw_jd),
    )


def _evidence_pack_for_prompt(pack: EvidencePack) -> str:
    bullet_lines = [
        f"- {bullet.ref} (target: {bullet.target}; score {bullet.score:.3f}): {bullet.text}"
        for bullet in pack.bullets
    ]
    skill_lines = [f"- /skills/{index}: {skill}" for index, skill in enumerate(pack.matched_skills)]
    snippet_lines = [f"- {snippet.ref}: {snippet.text}" for snippet in pack.jd_snippets]
    return (
        f"Company/team for salutation: {pack.company_or_team}\n"
        f"Role title if known: {pack.title or 'unknown'}\n\n"
        f"Resume bullet evidence:\n{chr(10).join(bullet_lines) or '- none'}\n\n"
        f"Matched skill evidence:\n{chr(10).join(skill_lines) or '- none'}\n\n"
        f"JD snippet evidence:\n{chr(10).join(snippet_lines) or '- none'}\n\n"
        f"Must-haves:\n{chr(10).join(f'- {item}' for item in pack.must_haves) or '- none'}"
    )


def _banned_phrase_violations(body: str) -> list[str]:
    lower = body.lower()
    phrases = [*get_settings().cover_letter_banned_phrases, "To Whom It May Concern"]
    return [f"banned phrase present: {phrase}" for phrase in phrases if phrase.lower() in lower]


def _structural_violations(body: str) -> list[str]:
    violations = _banned_phrase_violations(body)
    count = _word_count(body)
    if not MIN_WORDS <= count <= MAX_WORDS:
        violations.append(f"word count {count} outside {MIN_WORDS}-{MAX_WORDS}")
    paragraphs = [
        paragraph for paragraph in re.split(r"\n\s*\n", body.strip()) if paragraph.strip()
    ]
    if paragraphs and re.fullmatch(r"Dear .+ team,?", paragraphs[0].strip()):
        paragraphs = paragraphs[1:]
    if paragraphs and re.match(
        r"(?i)^(sincerely|best|regards|thank you)\b", paragraphs[-1].strip()
    ):
        paragraphs = paragraphs[:-1]
    if not 3 <= len(paragraphs) <= 4:
        violations.append(f"paragraph count {len(paragraphs)} outside 3-4")
    return violations


def _evidence_ref_violations(output: CoverLetterOutput, pack: EvidencePack) -> list[str]:
    if not output.claims_used:
        return ["claims_used is empty"]
    valid_refs = pack.refs
    return [
        f"claim uses unknown evidence_ref {claim.evidence_ref}"
        for claim in output.claims_used
        if claim.evidence_ref not in valid_refs
    ]


def _verification_violations(
    output: CoverLetterOutput,
    pack: EvidencePack,
    profile: StructuredResume,
    raw_jd: str,
) -> tuple[list[str], object]:
    claim_report = verify_prose(output.body_markdown, profile, raw_jd)
    violations = [
        *_structural_violations(output.body_markdown),
        *_evidence_ref_violations(output, pack),
        *claim_report.violations,
    ]
    return violations, claim_report


async def _generate_once(
    pack: EvidencePack,
    tone: Tone,
    *,
    model: str | None,
    retry_violations: list[str] | None = None,
) -> tuple[CoverLetterOutput, LLMUsage]:
    banned = ", ".join(get_settings().cover_letter_banned_phrases)
    retry_context = ""
    if retry_violations:
        retry_context = (
            "\n\nThe previous draft failed verification. Fix these issues without "
            "adding new facts:\n" + "\n".join(f"- {violation}" for violation in retry_violations)
        )
    user_content = (
        f"Tone: {tone}\n"
        f"Banned phrases: {banned}\n\n"
        f"Evidence pack:\n{_evidence_pack_for_prompt(pack)}"
        f"{retry_context}"
    )
    output, usage = await generate_structured(
        CoverLetterOutput,
        system=SYSTEM_PROMPT,
        user_content=user_content,
        model=model,
        max_tokens=4000,
    )
    return output, usage


async def generate_cover_letter(
    profile: StructuredResume,
    requirements: JobRequirements,
    raw_jd: str,
    resume_version: StructuredResume,
    tone: Tone = "standard",
    *,
    model: str | None = None,
) -> CoverLetterResult:
    pack = await _build_evidence_pack(resume_version, requirements, raw_jd)
    usage = LLMUsage()
    last_output: CoverLetterOutput | None = None
    last_claim_report = None
    last_violations: list[str] = []

    for attempt in range(2):
        output, item_usage = await _generate_once(
            pack,
            tone,
            model=model,
            retry_violations=last_violations if attempt else None,
        )
        usage += item_usage
        last_output = output
        violations, claim_report = _verification_violations(output, pack, profile, raw_jd)
        last_claim_report = claim_report
        if not violations:
            return CoverLetterResult(
                body_markdown=output.body_markdown,
                word_count=_word_count(output.body_markdown),
                claim_report=claim_report,
                usage=usage,
            )
        logger.warning("cover letter verification failed: %s", "; ".join(violations))
        last_violations = violations

    assert last_output is not None
    assert last_claim_report is not None
    raise ProseVerificationError(
        "cover letter failed verification after retry: " + "; ".join(last_violations)
    )


async def generate_cover_letter_for_job(
    session: AsyncSession,
    job_target_id: uuid.UUID,
    payload: CoverLetterRequest,
    *,
    model: str | None = None,
) -> CoverLetterResult:
    job_target = await session.get(JobTarget, job_target_id)
    if job_target is None:
        raise NotFoundError(f"job target {job_target_id} not found")

    version = await session.get(ResumeVersion, payload.resume_version_id)
    if version is None or version.job_target_id != job_target.id:
        raise NotFoundError(
            f"resume version {payload.resume_version_id} not found for job target {job_target_id}"
        )

    profile_row = await session.get(Profile, version.profile_id)
    if profile_row is None or profile_row.user_id != job_target.user_id:
        raise NotFoundError("resume version profile does not belong to this job target's user")

    if job_target.extracted_requirements is None:
        requirements, _ = await extract_requirements(job_target.raw_description, model=model)
        job_target.extracted_requirements = requirements.model_dump(mode="json")
        await session.flush()
    else:
        requirements = JobRequirements.model_validate(job_target.extracted_requirements)

    profile = StructuredResume.model_validate(profile_row.data)
    resume_version = StructuredResume.model_validate(version.data)
    result = await generate_cover_letter(
        profile,
        requirements,
        job_target.raw_description,
        resume_version,
        tone=payload.tone,
        model=model,
    )

    row = CoverLetter(
        job_target_id=job_target.id,
        resume_version_id=version.id,
        body_markdown=result.body_markdown,
        tone=CoverLetterTone(payload.tone),
        word_count=result.word_count,
        claim_report=result.claim_report.model_dump(mode="json"),
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            "a cover letter already exists for this job target, resume version, and tone"
        ) from exc
    await session.refresh(row)
    return result.model_copy(update={"id": row.id})


async def render_cover_letter_document(
    session: AsyncSession,
    cover_letter_id: uuid.UUID,
    payload: RenderRequest,
    *,
    expires_in: int = 900,
) -> RenderResponse:
    cover_letter = await session.get(CoverLetter, cover_letter_id)
    if cover_letter is None:
        raise NotFoundError(f"cover letter {cover_letter_id} not found")

    version = await session.get(ResumeVersion, cover_letter.resume_version_id)
    if version is None:
        raise NotFoundError(f"resume version {cover_letter.resume_version_id} not found")
    profile_row = await session.get(Profile, version.profile_id)
    if profile_row is None:
        raise NotFoundError(f"profile {version.profile_id} not found")

    profile = StructuredResume.model_validate(profile_row.data)
    if payload.format == "pdf":
        artifact = await anyio.to_thread.run_sync(
            lambda: render_cover_letter_pdf_result(
                profile,
                cover_letter.body_markdown,
                font_stack=payload.font or None,
                accent_color=payload.accent_color,
            )
        )
        kind = DocumentKind.cover_letter_pdf
        ext = "pdf"
        content_type = "application/pdf"
    else:
        artifact = await anyio.to_thread.run_sync(
            lambda: render_cover_letter_docx_result(
                profile,
                cover_letter.body_markdown,
                accent_color=payload.accent_color,
            )
        )
        kind = DocumentKind.cover_letter_docx
        ext = "docx"
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    s3_key = f"documents/{profile_row.user_id}/{version.id}/cover_letters/{cover_letter.id}.{ext}"
    await anyio.to_thread.run_sync(storage.put_object, s3_key, artifact.content, content_type)

    document = Document(resume_version_id=version.id, kind=kind, s3_key=s3_key)
    session.add(document)
    await session.commit()
    await session.refresh(document)

    download_url = await anyio.to_thread.run_sync(storage.presigned_get_url, s3_key, expires_in)
    return RenderResponse(
        document_id=document.id,
        kind=kind.value,
        s3_key=s3_key,
        download_url=download_url,
        expires_in=expires_in,
        page_count=artifact.page_count,
        warnings=artifact.warnings,
    )
