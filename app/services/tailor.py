"""Resume tailoring pipeline.

The core invariant is that accepted output is always a reordered/rephrased view
of the candidate's existing claims, never a source of new claims.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
import uuid

import anyio.to_thread
import numpy as np
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import JobTarget, Profile, ResumeVersion
from app.schemas.jd import JobRequirements
from app.schemas.llm import LLMUsage
from app.schemas.resume import Bullet, ExperienceItem, SkillGroup, StructuredResume
from app.schemas.tailor import (
    BulletRewrite,
    DiscardedRewrite,
    ExperienceRewriteOutput,
    TailorDiffEntry,
    TailorResult,
    TailorStats,
)
from app.services.claims import build_tech_lexicon, verify_rewrite
from app.services.errors import ConflictError, NotFoundError
from app.services.embeddings import embed_texts
from app.services.jd import extract_requirements
from app.services.llm import generate_structured
from app.services.score import score_resume

logger = logging.getLogger(__name__)

_BULLET_ADAPTER = TypeAdapter(Bullet)

SYSTEM_PROMPT = """\
You rewrite resume bullets for a specific job description while preserving the
candidate's original claims exactly.

Hard constraints:

- You may rephrase, reorder emphasis, surface implicit relevance, and mirror
  the JD's terminology ONLY where the underlying work plausibly matches.
- You may NOT add employers, titles, dates, tools, metrics, team sizes, or
  outcomes that are not stated or directly entailed by the original text.
- If a bullet cannot honestly be made more relevant, return it unchanged with
  claims_preserved=true and requirement_targeted=null. Unchanged is a valid,
  good outcome.
- Numbers are sacred: never introduce a number absent from the original; never
  alter an existing number.

Return exactly one object for every candidate bullet_ref, and no objects for
non-candidate sibling bullets. Keep every rewritten bullet concise enough for a
resume bullet and under 300 characters.
"""


@dataclass(frozen=True)
class RequirementTarget:
    term: str
    weight: float


@dataclass(frozen=True)
class BulletCandidate:
    bullet_ref: str
    experience_index: int
    bullet_index: int
    original: str
    score: float
    requirement_targeted: str | None


RewriteExperienceFn = Callable[
    [StructuredResume, JobRequirements, int, list[BulletCandidate], str | None],
    Awaitable[tuple[list[BulletRewrite], LLMUsage]],
]


def _json_ref(*parts: object) -> str:
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _requirement_targets(requirements: JobRequirements) -> list[RequirementTarget]:
    targets: dict[str, float] = {}

    def add(term: str, weight: float) -> None:
        stripped = term.strip()
        if not stripped:
            return
        current = targets.get(stripped)
        targets[stripped] = max(weight, current or 0.0)

    for item in requirements.hard_skills:
        add(item.term, item.weight)
    for must_have in requirements.must_haves:
        add(must_have, 1.0)

    return [RequirementTarget(term=term, weight=weight) for term, weight in targets.items()]


def _all_bullet_refs(profile: StructuredResume) -> list[tuple[str, str, int | None, int | None]]:
    refs: list[tuple[str, str, int | None, int | None]] = []
    for i, item in enumerate(profile.experience):
        for j, bullet in enumerate(item.bullets):
            refs.append((_json_ref("experience", i, "bullets", j), bullet, i, j))
    for i, project in enumerate(profile.projects):
        for j, bullet in enumerate(project.bullets):
            refs.append((_json_ref("projects", i, "bullets", j), bullet, None, None))
    return refs


def _recent_experience_indices(profile: StructuredResume) -> set[int]:
    return set(range(min(2, len(profile.experience))))


async def _embed(texts: list[str]) -> np.ndarray:
    return await anyio.to_thread.run_sync(embed_texts, texts)


async def _score_candidates(
    profile: StructuredResume,
    requirements: JobRequirements,
    *,
    relevance_threshold: float,
    max_rewrites: int,
) -> tuple[list[BulletCandidate], int]:
    refs = _all_bullet_refs(profile)
    targets = _requirement_targets(requirements)
    if not refs or not targets:
        return [], len(refs)

    bullet_vectors = await _embed([bullet for _, bullet, _, _ in refs])
    requirement_vectors = await _embed([target.term for target in targets])
    similarities = bullet_vectors @ requirement_vectors.T
    weights = np.asarray([target.weight for target in targets], dtype=np.float32)
    weighted = similarities * weights

    recent_indices = _recent_experience_indices(profile)
    candidates: list[BulletCandidate] = []
    for row, (bullet_ref, bullet, experience_index, bullet_index) in enumerate(refs):
        best_index = int(np.argmax(weighted[row]))
        score = float(weighted[row][best_index])
        if (
            experience_index is not None
            and bullet_index is not None
            and experience_index in recent_indices
            and score < relevance_threshold
        ):
            candidates.append(
                BulletCandidate(
                    bullet_ref=bullet_ref,
                    experience_index=experience_index,
                    bullet_index=bullet_index,
                    original=bullet,
                    score=score,
                    requirement_targeted=targets[best_index].term,
                )
            )

    candidates.sort(key=lambda candidate: candidate.score)
    return candidates[:max_rewrites], len(refs)


def _requirements_for_prompt(requirements: JobRequirements) -> str:
    hard_skills = "\n".join(
        f"- {item.term} (weight {item.weight:.2f}; evidence: {item.evidence})"
        for item in requirements.hard_skills
    )
    must_haves = "\n".join(f"- {item}" for item in requirements.must_haves)
    domain_terms = ", ".join(requirements.domain_terms) or "none"
    return (
        "Hard skills:\n"
        f"{hard_skills or '- none'}\n\n"
        "Must-haves:\n"
        f"{must_haves or '- none'}\n\n"
        f"Domain terms worth mirroring only when truthful: {domain_terms}"
    )


def _profile_skill_context(profile: StructuredResume) -> str:
    skills = [
        f"{group.category}: {', '.join(group.items)}" for group in profile.skills if group.items
    ]
    technologies = sorted(
        {technology for item in profile.experience for technology in item.technologies}
        | {technology for project in profile.projects for technology in project.technologies}
    )
    lines = []
    if skills:
        lines.append("Skills: " + " | ".join(skills))
    if technologies:
        lines.append("Technologies named in roles/projects: " + ", ".join(technologies))
    return "\n".join(lines) or "No separate skill context provided."


def _experience_for_prompt(item: ExperienceItem, index: int) -> str:
    lines = [
        f"Experience item {index}",
        f"Company: {item.company}",
        f"Title: {item.title}",
        f"Dates: {item.start_date} to {item.end_date or 'present'}",
        f"Technologies listed on item: {', '.join(item.technologies) or 'none'}",
        "Sibling bullets:",
    ]
    for bullet_index, bullet in enumerate(item.bullets):
        lines.append(f"- {_json_ref('experience', index, 'bullets', bullet_index)}: {bullet}")
    return "\n".join(lines)


def _candidates_for_prompt(candidates: list[BulletCandidate]) -> str:
    return "\n".join(
        (
            f"- {candidate.bullet_ref} (score {candidate.score:.3f}; target "
            f"{candidate.requirement_targeted!r}): {candidate.original}"
        )
        for candidate in candidates
    )


async def _rewrite_experience_item(
    profile: StructuredResume,
    requirements: JobRequirements,
    experience_index: int,
    candidates: list[BulletCandidate],
    model: str | None,
) -> tuple[list[BulletRewrite], LLMUsage]:
    item = profile.experience[experience_index]
    user_content = (
        f"{_experience_for_prompt(item, experience_index)}\n\n"
        f"Candidate bullets to consider:\n{_candidates_for_prompt(candidates)}\n\n"
        f"Job requirements:\n{_requirements_for_prompt(requirements)}\n\n"
        f"Candidate-wide skill context:\n{_profile_skill_context(profile)}"
    )
    output, usage = await generate_structured(
        ExperienceRewriteOutput,
        system=SYSTEM_PROMPT,
        user_content=user_content,
        model=model,
        validate_extra=lambda parsed: parsed,
    )
    return output.rewrites, usage


def _group_candidates(
    candidates: list[BulletCandidate],
) -> list[tuple[int, list[BulletCandidate]]]:
    grouped: dict[int, list[BulletCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.experience_index, []).append(candidate)
    return sorted(grouped.items())


def _rewrite_validation_reasons(
    rewrite: BulletRewrite,
    candidate: BulletCandidate,
    profile: StructuredResume,
    requirements: JobRequirements,
) -> list[str]:
    reasons: list[str] = []
    if rewrite.original.strip() != candidate.original.strip():
        reasons.append("model returned an original bullet that does not match the candidate")
    if not rewrite.claims_preserved:
        reasons.append("model marked claims_preserved=false")
    try:
        _BULLET_ADAPTER.validate_python(rewrite.rewritten.strip())
    except ValidationError as exc:
        reasons.append(f"rewritten bullet violates resume schema: {exc.errors()[0]['msg']}")

    parent = profile.experience[candidate.experience_index]
    verification = verify_rewrite(
        original=candidate.original,
        rewritten=rewrite.rewritten.strip(),
        profile=profile,
        requirements=requirements,
        parent_experience=parent,
    )
    reasons.extend(verification.reasons)
    return reasons


def _apply_bullet_rewrite(
    resume: StructuredResume,
    candidate: BulletCandidate,
    rewrite: BulletRewrite,
) -> None:
    resume.experience[candidate.experience_index].bullets[candidate.bullet_index] = (
        rewrite.rewritten.strip()
    )


def _skill_requirement_terms(requirements: JobRequirements) -> set[str]:
    terms = {_normalize_skill_key(item.term) for item in requirements.hard_skills}
    terms.update(_normalize_skill_key(item) for item in requirements.must_haves)
    terms.update(_normalize_skill_key(item) for item in requirements.nice_to_haves)
    terms.update(_normalize_skill_key(item) for item in requirements.domain_terms)
    return {term for term in terms if term}


def _normalize_skill_key(value: str) -> str:
    return value.strip().lower()


def _skill_matches_jd(skill: str, requirement_terms: set[str], tech_lexicon: set[str]) -> bool:
    normalized = _normalize_skill_key(skill)
    lexicon_terms = {_normalize_skill_key(term) for term in tech_lexicon}
    for term in requirement_terms | lexicon_terms:
        if not term:
            continue
        if normalized == term or normalized in term or term in normalized:
            return True
    return False


def _reorder_skills(
    resume: StructuredResume, requirements: JobRequirements
) -> tuple[list[SkillGroup], bool, str | None]:
    if not resume.skills:
        return resume.skills, False, None

    requirement_terms = _skill_requirement_terms(requirements)
    tech_lexicon = build_tech_lexicon(requirements, resume)
    changed = False
    reordered_groups: list[tuple[bool, int, SkillGroup]] = []

    for index, group in enumerate(resume.skills):
        matched = [
            item for item in group.items if _skill_matches_jd(item, requirement_terms, tech_lexicon)
        ]
        unmatched = [
            item
            for item in group.items
            if not _skill_matches_jd(item, requirement_terms, tech_lexicon)
        ]
        reordered_items = matched + unmatched
        if reordered_items != group.items:
            changed = True
        reordered_groups.append(
            (
                bool(matched),
                index,
                SkillGroup(category=group.category, items=reordered_items),
            )
        )

    reordered_groups.sort(key=lambda row: (not row[0], row[1]))
    groups = [group for _, _, group in reordered_groups]
    if [group.category for group in groups] != [group.category for group in resume.skills]:
        changed = True

    target = ", ".join(
        item.term
        for item in sorted(requirements.hard_skills, key=lambda item: item.weight, reverse=True)
    )
    return groups, changed, target or None


async def tailor(
    profile: StructuredResume,
    requirements: JobRequirements,
    *,
    relevance_threshold: float | None = None,
    max_rewrites: int | None = None,
    model: str | None = None,
    rewrite_experience_item: RewriteExperienceFn | None = None,
) -> TailorResult:
    """Tailor a structured resume to a job's requirements."""
    settings = get_settings()
    threshold = (
        relevance_threshold if relevance_threshold is not None else settings.relevance_threshold
    )
    rewrite_cap = max_rewrites if max_rewrites is not None else settings.max_rewrites
    rewrite_fn = rewrite_experience_item or _rewrite_experience_item

    candidates, bullets_scored = await _score_candidates(
        profile,
        requirements,
        relevance_threshold=threshold,
        max_rewrites=rewrite_cap,
    )
    candidate_by_ref = {candidate.bullet_ref: candidate for candidate in candidates}
    tailored = profile.model_copy(deep=True)
    diff: list[TailorDiffEntry] = []
    discarded: list[DiscardedRewrite] = []
    usage = LLMUsage()
    rewrites_returned = 0

    for experience_index, item_candidates in _group_candidates(candidates):
        rewrites, item_usage = await rewrite_fn(
            profile, requirements, experience_index, item_candidates, model
        )
        usage += item_usage
        rewrites_returned += len(rewrites)
        seen_refs: set[str] = set()
        for rewrite in rewrites:
            seen_refs.add(rewrite.bullet_ref)
            candidate = candidate_by_ref.get(rewrite.bullet_ref)
            if candidate is None:
                logger.warning("discarding rewrite for unknown ref %s", rewrite.bullet_ref)
                discarded.append(
                    DiscardedRewrite(
                        bullet_ref=rewrite.bullet_ref,
                        before=rewrite.original,
                        proposed=rewrite.rewritten,
                        reasons=["model returned a non-candidate bullet_ref"],
                        requirement_targeted=rewrite.requirement_targeted,
                    )
                )
                continue

            reasons = _rewrite_validation_reasons(rewrite, candidate, profile, requirements)
            if reasons:
                logger.warning(
                    "discarding rewrite bullet_ref=%s reasons=%s",
                    rewrite.bullet_ref,
                    "; ".join(reasons),
                )
                discarded.append(
                    DiscardedRewrite(
                        bullet_ref=rewrite.bullet_ref,
                        before=candidate.original,
                        proposed=rewrite.rewritten,
                        reasons=reasons,
                        requirement_targeted=rewrite.requirement_targeted,
                    )
                )
                continue

            rewritten = rewrite.rewritten.strip()
            if rewritten == candidate.original:
                continue

            _apply_bullet_rewrite(tailored, candidate, rewrite)
            diff.append(
                TailorDiffEntry(
                    bullet_ref=candidate.bullet_ref,
                    before=candidate.original,
                    after=rewritten,
                    requirement_targeted=rewrite.requirement_targeted
                    or candidate.requirement_targeted,
                )
            )

        missing_refs = {candidate.bullet_ref for candidate in item_candidates} - seen_refs
        for ref in sorted(missing_refs):
            candidate = candidate_by_ref[ref]
            discarded.append(
                DiscardedRewrite(
                    bullet_ref=ref,
                    before=candidate.original,
                    proposed=candidate.original,
                    reasons=["model omitted candidate bullet_ref"],
                    requirement_targeted=candidate.requirement_targeted,
                )
            )

    before_skills = [group.model_dump(mode="json") for group in tailored.skills]
    reordered_skills, skills_changed, skills_target = _reorder_skills(tailored, requirements)
    if skills_changed:
        tailored.skills = reordered_skills
        diff.append(
            TailorDiffEntry(
                bullet_ref="/skills",
                before=before_skills,
                after=[group.model_dump(mode="json") for group in tailored.skills],
                requirement_targeted=skills_target,
            )
        )

    tailored = StructuredResume.model_validate(tailored.model_dump(mode="json"))
    stats = TailorStats(
        bullets_scored=bullets_scored,
        rewrite_candidates=len(candidates),
        experience_items_rewritten=len(_group_candidates(candidates)),
        rewrites_requested=len(candidates),
        rewrites_returned=rewrites_returned,
        rewrites_accepted=sum(1 for entry in diff if entry.bullet_ref != "/skills"),
        rewrites_discarded=len(discarded),
        skills_reordered=skills_changed,
        relevance_threshold=threshold,
        max_rewrites=rewrite_cap,
        usage=usage,
    )
    return TailorResult(resume=tailored, diff=diff, stats=stats, discarded_rewrites=discarded)


async def tailor_profile_for_job(
    session: AsyncSession,
    profile_id: uuid.UUID,
    job_target_id: uuid.UUID,
    *,
    model: str | None = None,
) -> TailorResult:
    profile_row = await session.get(Profile, profile_id)
    if profile_row is None:
        raise NotFoundError(f"profile {profile_id} not found")

    job_target = await session.get(JobTarget, job_target_id)
    if job_target is None or job_target.user_id != profile_row.user_id:
        raise NotFoundError(f"job target {job_target_id} not found for this profile's user")

    if job_target.extracted_requirements is None:
        requirements, _ = await extract_requirements(job_target.raw_description)
        job_target.extracted_requirements = requirements.model_dump(mode="json")
        await session.flush()
    else:
        requirements = JobRequirements.model_validate(job_target.extracted_requirements)

    profile = StructuredResume.model_validate(profile_row.data)
    result = await tailor(profile, requirements, model=model)
    score_before, score_after = await anyio.to_thread.run_sync(
        lambda: (score_resume(profile, requirements), score_resume(result.resume, requirements))
    )
    version = ResumeVersion(
        profile_id=profile_row.id,
        job_target_id=job_target.id,
        data=result.resume.model_dump(mode="json"),
        diff={
            "changes": [entry.model_dump(mode="json") for entry in result.diff],
            "stats": result.stats.model_dump(mode="json"),
            "discarded_rewrites": [
                rewrite.model_dump(mode="json") for rewrite in result.discarded_rewrites
            ],
            "score_before": score_before.model_dump(mode="json"),
            "score_after": score_after.model_dump(mode="json"),
        },
        label=f"Tailored for {job_target.company or job_target.title or 'job target'}",
    )
    session.add(version)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            f"a resume version for job target {job_target_id} already exists on this profile"
        ) from exc
    await session.refresh(version)
    return result.model_copy(
        update={"version_id": version.id, "score_before": score_before, "score_after": score_after}
    )
