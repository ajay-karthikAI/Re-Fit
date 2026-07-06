"""Shared evidence-pack construction for grounded prose generation.

Cover letters, follow-up emails, and short-answer form responses all draw from
the same deliberately-small evidence pack: the resume bullets and skills that
best match the job requirements, plus the JD snippets that back any company or
role claim. Keeping this in one place is what lets every generator enforce the
same non-fabrication discipline (see CLAUDE.md) instead of re-deriving it.

No LLM calls live here — this is deterministic retrieval and formatting.
"""

from dataclasses import dataclass
import re

import anyio.to_thread
import numpy as np
from rapidfuzz import fuzz

from app.schemas.cover_letter import ClaimUsed
from app.schemas.jd import JobRequirements
from app.schemas.resume import StructuredResume
from app.services.embeddings import embed_texts


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


def word_count(text: str) -> int:
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


def guess_company_or_team(raw_jd: str) -> str:
    for pattern in [
        r"(?im)^[^\n—-]+\s+[—-]\s+([A-Z][^\n(,;]+)",
        r"(?im)^\s*company\s*:\s*([A-Z][^\n,.;]+)",
        r"(?im)^\s*about\s+([A-Z][A-Za-z0-9& .'-]+)\s*$",
    ]:
        match = re.search(pattern, raw_jd)
        if match and match.group(1).strip().lower() not in {"us", "the role", "the company"}:
            return match.group(1).strip()
    return "hiring"


def guess_title(raw_jd: str) -> str | None:
    for pattern in [
        r"(?im)^\s*title\s*:\s*([^\n]+)",
        r"(?im)^\s*role\s*:\s*([^\n]+)",
    ]:
        match = re.search(pattern, raw_jd)
        if match:
            return match.group(1).strip()
    return None


async def build_evidence_pack(
    resume_version: StructuredResume,
    requirements: JobRequirements,
    raw_jd: str,
) -> EvidencePack:
    return EvidencePack(
        bullets=await _evidence_bullets(resume_version, requirements),
        matched_skills=_matched_skills(resume_version, requirements),
        jd_snippets=_jd_snippets(raw_jd, requirements),
        must_haves=requirements.must_haves,
        company_or_team=guess_company_or_team(raw_jd),
        title=guess_title(raw_jd),
    )


def evidence_pack_for_prompt(pack: EvidencePack) -> str:
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


def evidence_ref_violations(claims_used: list[ClaimUsed], pack: EvidencePack) -> list[str]:
    """Every claim must cite an evidence_ref that exists in the pack."""
    if not claims_used:
        return ["claims_used is empty"]
    valid_refs = pack.refs
    return [
        f"claim uses unknown evidence_ref {claim.evidence_ref}"
        for claim in claims_used
        if claim.evidence_ref not in valid_refs
    ]
