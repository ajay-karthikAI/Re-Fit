"""Deterministic ATS-style resume scoring.

No LLM calls belong in this module. It scores a StructuredResume against already
extracted JobRequirements using local text matching, local embeddings, schema
checks, and an optional renderer round-trip.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil
import re
import uuid
from typing import Protocol

import anyio.to_thread
import numpy as np
from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobTarget, Profile, ResumeVersion
from app.schemas.jd import JobRequirements
from app.schemas.resume import StructuredResume
from app.schemas.score import (
    ATSScore,
    FormatHealthBreakdown,
    KeywordCoverageBreakdown,
    LengthDensityBreakdown,
    ScoreComponent,
    SectionCheck,
    SectionIntegrityBreakdown,
    TermCoverage,
)
from app.services.embeddings import embed_texts
from app.services.errors import ConflictError, NotFoundError
from app.services.extract import extract_text
from app.services.render import ClassicResumeRenderer
from app.services.score_cache import build_score_cache

KEYWORD_COVERAGE_WEIGHT = 0.50
SECTION_INTEGRITY_WEIGHT = 0.15
FORMAT_HEALTH_WEIGHT = 0.15
LENGTH_DENSITY_WEIGHT = 0.20

TEXT_COVERAGE_THRESHOLD = 90.0
EMBEDDING_COVERAGE_THRESHOLD = 0.60
FORMAT_MATCH_THRESHOLD = 90.0
FORMAT_HEALTH_TARGET = 0.95
WORDS_PER_PAGE = 450

_YEAR_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+.#'-]*")
_FIRST_PERSON_RE = re.compile(r"\b(?:i|me|my|mine|we|our|ours)\b", re.IGNORECASE)

_embed_texts = embed_texts


class ResumeRenderer(Protocol):
    """Future renderer contract for format-health round trips."""

    def render_pdf(self, resume: StructuredResume) -> bytes:
        """Render a resume to PDF bytes."""


@dataclass(frozen=True)
class RequirementTarget:
    term: str
    weight: float


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _requirement_targets(requirements: JobRequirements) -> list[RequirementTarget]:
    targets: dict[str, RequirementTarget] = {}

    def add(term: str, weight: float) -> None:
        stripped = term.strip()
        if not stripped:
            return
        key = _normalize(stripped)
        current = targets.get(key)
        if current is None or weight > current.weight:
            targets[key] = RequirementTarget(term=stripped, weight=weight)

    for item in requirements.hard_skills:
        add(item.term, item.weight)
    for must_have in requirements.must_haves:
        add(must_have, 1.0)

    return list(targets.values())


def _resume_text(resume: StructuredResume) -> str:
    parts: list[str] = [
        resume.contact.full_name,
        resume.contact.email,
        resume.contact.phone or "",
        resume.contact.location or "",
        str(resume.contact.linkedin_url or ""),
        str(resume.contact.github_url or ""),
        str(resume.contact.portfolio_url or ""),
        resume.summary or "",
    ]
    for item in resume.experience:
        parts.extend(
            [
                item.company,
                item.title,
                item.location or "",
                item.start_date,
                item.end_date or "present",
                " ".join(item.technologies),
                *item.bullets,
            ]
        )
    for item in resume.education:
        parts.extend(
            [
                item.institution,
                item.degree,
                item.field or "",
                item.graduation_date or "",
                " ".join(item.details),
            ]
        )
    for group in resume.skills:
        parts.extend([group.category, " ".join(group.items)])
    for project in resume.projects:
        parts.extend(
            [
                project.name,
                project.description or "",
                " ".join(project.technologies),
                str(project.url or ""),
                *project.bullets,
            ]
        )
    return "\n".join(part for part in parts if part)


def _bullet_texts(resume: StructuredResume) -> list[str]:
    bullets: list[str] = []
    for item in resume.experience:
        bullets.extend(item.bullets)
    for project in resume.projects:
        bullets.extend(project.bullets)
    return bullets


def _text_match_score(term: str, resume_text: str) -> float:
    normalized_term = _normalize(term)
    normalized_resume = _normalize(resume_text)
    if not normalized_term:
        return 0.0
    if normalized_term in normalized_resume:
        return 100.0
    return float(fuzz.partial_ratio(normalized_term, normalized_resume))


def _embedding_scores(terms: Sequence[str], bullets: Sequence[str]) -> dict[str, float]:
    if not terms or not bullets:
        return {term: 0.0 for term in terms}
    term_vectors = _embed_texts(list(terms))
    bullet_vectors = _embed_texts(list(bullets))
    similarities = term_vectors @ bullet_vectors.T
    return {
        term: float(np.max(similarities[index])) if similarities.shape[1] else 0.0
        for index, term in enumerate(terms)
    }


def _score_keyword_coverage(
    resume: StructuredResume, requirements: JobRequirements
) -> KeywordCoverageBreakdown:
    targets = _requirement_targets(requirements)
    if not targets:
        return KeywordCoverageBreakdown(score=100.0)

    resume_text = _resume_text(resume)
    bullets = _bullet_texts(resume)
    text_scores = {target.term: _text_match_score(target.term, resume_text) for target in targets}
    embedding_needed = [
        target.term for target in targets if text_scores[target.term] < TEXT_COVERAGE_THRESHOLD
    ]
    embedding_scores = _embedding_scores(embedding_needed, bullets)

    covered_weight = 0.0
    total_weight = sum(target.weight for target in targets)
    term_results: list[TermCoverage] = []
    covered_terms: list[str] = []
    missing_terms: list[str] = []

    for target in targets:
        text_score = text_scores[target.term]
        embedding_similarity = embedding_scores.get(target.term)
        text_covered = text_score >= TEXT_COVERAGE_THRESHOLD
        embedding_covered = (
            embedding_similarity is not None
            and embedding_similarity >= EMBEDDING_COVERAGE_THRESHOLD
        )
        covered = text_covered or embedding_covered
        if covered:
            covered_weight += target.weight
            covered_terms.append(target.term)
        else:
            missing_terms.append(target.term)

        match_type = "text" if text_covered else "embedding" if embedding_covered else "none"
        term_results.append(
            TermCoverage(
                term=target.term,
                weight=_round(target.weight) or 0.0,
                covered=covered,
                match_type=match_type,
                text_match_score=_round(text_score),
                embedding_similarity=_round(embedding_similarity),
            )
        )

    score = 100.0 if total_weight == 0 else (covered_weight / total_weight) * 100.0
    return KeywordCoverageBreakdown(
        score=_round(score) or 0.0,
        covered_terms=covered_terms,
        missing_terms=missing_terms,
        terms=term_results,
    )


def _valid_year_month(value: str | None) -> bool:
    if value is None:
        return True
    return bool(_YEAR_MONTH_RE.fullmatch(value))


def _score_section_integrity(resume: StructuredResume) -> SectionIntegrityBreakdown:
    required_fields_ok = bool(resume.experience) and all(
        item.company.strip() and item.title.strip() and item.start_date.strip() and item.bullets
        for item in resume.experience
    )
    dates_ok = bool(resume.experience) and all(
        _valid_year_month(item.start_date)
        and _valid_year_month(item.end_date)
        and (item.end_date is None or item.end_date >= item.start_date)
        for item in resume.experience
    )
    checks = [
        SectionCheck(
            name="contact_email",
            passed=bool(str(resume.contact.email).strip()),
            detail="contact email present",
        ),
        SectionCheck(
            name="experience",
            passed=bool(resume.experience),
            detail="experience section non-empty",
        ),
        SectionCheck(
            name="education",
            passed=bool(resume.education),
            detail="education section present",
        ),
        SectionCheck(
            name="skills",
            passed=bool(resume.skills),
            detail="skills section present",
        ),
        SectionCheck(
            name="experience_required_fields",
            passed=required_fields_ok,
            detail="company, title, start date, and bullets present on each experience item",
        ),
        SectionCheck(
            name="experience_dates",
            passed=dates_ok,
            detail="experience dates parse as YYYY-MM and end dates do not precede start dates",
        ),
    ]
    passed = sum(1 for check in checks if check.passed)
    return SectionIntegrityBreakdown(
        score=_round((passed / len(checks)) * 100.0) or 0.0, checks=checks
    )


def _score_format_health(
    resume: StructuredResume, renderer: ResumeRenderer
) -> FormatHealthBreakdown:
    bullets = _bullet_texts(resume)
    if not bullets:
        return FormatHealthBreakdown(
            score=100.0,
            renderer_available=True,
            match_rate=1.0,
            matched_bullets=0,
            total_bullets=0,
            notes=["no bullets to round-trip"],
        )

    try:
        rendered = renderer.render_pdf(resume)
        extracted = extract_text(rendered, "resume.pdf")
    except Exception as exc:
        return FormatHealthBreakdown(
            score=0.0,
            renderer_available=True,
            match_rate=0.0,
            matched_bullets=0,
            total_bullets=len(bullets),
            notes=[f"render/extract round-trip failed: {exc}"],
        )

    haystack = extracted.raw_text.lower()
    matched = sum(
        1
        for bullet in bullets
        if fuzz.partial_ratio(bullet.lower(), haystack) >= FORMAT_MATCH_THRESHOLD
    )
    match_rate = matched / len(bullets)
    score = (
        100.0 if match_rate >= FORMAT_HEALTH_TARGET else (match_rate / FORMAT_HEALTH_TARGET) * 100.0
    )
    notes = []
    if match_rate < FORMAT_HEALTH_TARGET:
        notes.append("less than 95% of bullets survived PDF extraction")
    return FormatHealthBreakdown(
        score=_round(score),
        renderer_available=True,
        match_rate=_round(match_rate),
        matched_bullets=matched,
        total_bullets=len(bullets),
        notes=notes,
    )


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _page_score(estimated_pages: int) -> tuple[float, str | None]:
    if estimated_pages in {1, 2}:
        return 1.0, None
    if estimated_pages == 0:
        return 0.5, "resume appears empty"
    if estimated_pages == 3:
        return 0.7, "estimated at 3 pages; 1-2 pages is ideal"
    if estimated_pages == 4:
        return 0.4, "estimated at 4 pages; 1-2 pages is ideal"
    return 0.2, f"estimated at {estimated_pages} pages; 1-2 pages is ideal"


def _bullet_count_score(count: int) -> float:
    if 3 <= count <= 6:
        return 1.0
    if count in {2, 7}:
        return 0.75
    if count in {1, 8}:
        return 0.5
    return 0.25


def _average_bullet_length_score(average_words: float) -> tuple[float, str | None]:
    if 8 <= average_words <= 30:
        return 1.0, None
    if 5 <= average_words < 8 or 30 < average_words <= 35:
        return 0.75, "average bullet length is slightly outside the 8-30 word target"
    if 1 <= average_words < 5 or 35 < average_words <= 45:
        return 0.5, "average bullet length is outside the 8-30 word target"
    return 0.25, "average bullet length is far outside the 8-30 word target"


def _score_length_density(resume: StructuredResume) -> LengthDensityBreakdown:
    text = _resume_text(resume)
    words = _words(text)
    word_count = len(words)
    estimated_pages = ceil(word_count / WORDS_PER_PAGE) if word_count else 0
    page_score, page_note = _page_score(estimated_pages)

    recent_counts = [len(item.bullets) for item in resume.experience[:2]]
    recent_score = (
        sum(_bullet_count_score(count) for count in recent_counts) / len(recent_counts)
        if recent_counts
        else 0.0
    )
    bullet_words = [len(_words(bullet)) for bullet in _bullet_texts(resume)]
    average_bullet_words = sum(bullet_words) / len(bullet_words) if bullet_words else 0.0
    bullet_length_score, bullet_length_note = _average_bullet_length_score(average_bullet_words)
    pronoun_count = len(_FIRST_PERSON_RE.findall(text))
    pronoun_score = max(0.0, 1.0 - (0.2 * pronoun_count))

    notes = []
    if page_note:
        notes.append(page_note)
    if recent_counts and any(count < 3 or count > 6 for count in recent_counts):
        notes.append("recent roles should usually have 3-6 bullets each")
    if bullet_length_note:
        notes.append(bullet_length_note)
    if pronoun_count:
        notes.append(f"found {pronoun_count} first-person pronoun(s)")

    score = (
        page_score * 0.35 + recent_score * 0.25 + bullet_length_score * 0.25 + pronoun_score * 0.15
    ) * 100.0
    return LengthDensityBreakdown(
        score=_round(score) or 0.0,
        estimated_pages=estimated_pages,
        word_count=word_count,
        average_bullet_words=_round(average_bullet_words) or 0.0,
        recent_role_bullet_counts=recent_counts,
        first_person_pronouns=pronoun_count,
        notes=notes,
    )


def _component(
    *,
    name: str,
    label: str,
    score: float | None,
    weight: float,
    notes: list[str] | None = None,
) -> ScoreComponent:
    included = score is not None
    weighted_points = None if score is None else score * weight
    return ScoreComponent(
        name=name,  # type: ignore[arg-type]
        label=label,
        score=_round(score),
        weight=weight,
        included=included,
        weighted_points=_round(weighted_points),
        notes=notes or [],
    )


def score_resume(
    resume: StructuredResume,
    requirements: JobRequirements,
    renderer: ResumeRenderer | None = None,
) -> ATSScore:
    """Score a structured resume against already-extracted job requirements."""
    renderer = renderer or ClassicResumeRenderer()
    keyword = _score_keyword_coverage(resume, requirements)
    section = _score_section_integrity(resume)
    format_health = _score_format_health(resume, renderer)
    length_density = _score_length_density(resume)

    raw_components = [
        ("keyword_coverage", "Keyword coverage", keyword.score, KEYWORD_COVERAGE_WEIGHT, []),
        ("section_integrity", "Section integrity", section.score, SECTION_INTEGRITY_WEIGHT, []),
        (
            "format_health",
            "Format health",
            format_health.score,
            FORMAT_HEALTH_WEIGHT,
            format_health.notes,
        ),
        (
            "length_and_density",
            "Length and density",
            length_density.score,
            LENGTH_DENSITY_WEIGHT,
            length_density.notes,
        ),
    ]
    components = [
        _component(
            name=name,
            label=label,
            score=score,
            weight=weight,
            notes=notes,
        )
        for name, label, score, weight, notes in raw_components
    ]
    headline = sum(component.weighted_points or 0.0 for component in components)
    return ATSScore(
        headline_score=_round(headline) or 0.0,
        components=components,
        keyword_coverage=keyword,
        section_integrity=section,
        format_health=format_health,
        length_and_density=length_density,
    )


async def score_resume_version(
    session: AsyncSession,
    version_id: uuid.UUID,
    job_target_id: uuid.UUID,
    renderer: ResumeRenderer | None = None,
) -> ATSScore:
    version = await session.get(ResumeVersion, version_id)
    if version is None or version.deleted_at is not None:
        raise NotFoundError(f"resume version {version_id} not found")

    profile = await session.get(Profile, version.profile_id)
    if profile is None:
        raise NotFoundError(f"profile {version.profile_id} not found")

    job_target = await session.get(JobTarget, job_target_id)
    if job_target is None or job_target.user_id != profile.user_id:
        raise NotFoundError(f"job target {job_target_id} not found for this resume version")
    if job_target.extracted_requirements is None:
        raise ConflictError(f"job target {job_target_id} has no extracted requirements")

    resume = StructuredResume.model_validate(version.data)
    requirements = JobRequirements.model_validate(job_target.extracted_requirements)
    score = await anyio.to_thread.run_sync(
        lambda: score_resume(resume, requirements, renderer=renderer)
    )
    version.score_cache = build_score_cache(job_target.id, score)
    await session.commit()
    return score
