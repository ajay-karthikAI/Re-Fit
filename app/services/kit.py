"""ApplicationKit orchestration for one job target."""

import uuid

import anyio.to_thread
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Application,
    CoverLetter,
    CoverLetterTone,
    Document,
    DocumentKind,
    Followup,
    JobTarget,
    Profile,
)
from app.models import ResumeVersion
from app.schemas.cover_letter import Tone
from app.schemas.followup import FollowupRead
from app.schemas.jd import JobRequirements
from app.schemas.kit import (
    ApplicationKitDetail,
    KitClaimSummary,
    KitCoverLetterDetail,
    KitDiffSummary,
    KitRequest,
    KitResult,
    KitVersionDetail,
)
from app.schemas.llm import LLMUsage
from app.schemas.render import RenderRequest
from app.schemas.resume import StructuredResume
from app.schemas.score import ATSScore
from app.services import storage
from app.services.cover_letter import generate_cover_letter, render_cover_letter_document
from app.services.errors import KitMissingPiecesError, NotFoundError
from app.services.jd import extract_requirements
from app.services.render import render_version_document
from app.services.score import score_resume
from app.services.score_cache import build_score_cache, headline_from_cache
from app.services.tailor import tailor


async def _canonical_profile(session: AsyncSession, user_id: uuid.UUID) -> Profile | None:
    result = await session.execute(
        select(Profile).where(Profile.user_id == user_id, Profile.is_canonical)
    )
    return result.scalar_one_or_none()


async def _tailored_version(
    session: AsyncSession, profile_id: uuid.UUID, job_target_id: uuid.UUID
) -> ResumeVersion | None:
    result = await session.execute(
        select(ResumeVersion).where(
            ResumeVersion.profile_id == profile_id,
            ResumeVersion.job_target_id == job_target_id,
            ResumeVersion.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _document(
    session: AsyncSession,
    version_id: uuid.UUID,
    kind: DocumentKind,
    *,
    s3_key: str | None = None,
) -> Document | None:
    statement = select(Document).where(
        Document.resume_version_id == version_id,
        Document.kind == kind,
    )
    if s3_key is not None:
        statement = statement.where(Document.s3_key == s3_key)
    statement = statement.order_by(Document.created_at.desc())
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def _cover_letter(
    session: AsyncSession,
    job_target_id: uuid.UUID,
    version_id: uuid.UUID,
    tone: Tone,
) -> CoverLetter | None:
    result = await session.execute(
        select(CoverLetter)
        .where(
            CoverLetter.job_target_id == job_target_id,
            CoverLetter.resume_version_id == version_id,
            CoverLetter.tone == CoverLetterTone(tone),
        )
        .order_by(CoverLetter.created_at.desc())
    )
    return result.scalar_one_or_none()


async def _requirements_for_post(
    session: AsyncSession,
    job_target: JobTarget,
    *,
    model: str | None = None,
) -> tuple[JobRequirements, LLMUsage]:
    if job_target.extracted_requirements is None:
        requirements, extraction_usage = await extract_requirements(
            job_target.raw_description,
            model=model,
        )
        job_target.extracted_requirements = requirements.model_dump(mode="json")
        await session.flush()
        return requirements, extraction_usage
    return JobRequirements.model_validate(job_target.extracted_requirements), LLMUsage()


def _scores_from_diff(diff: dict | None) -> tuple[ATSScore | None, ATSScore | None]:
    if not diff:
        return None, None
    try:
        before = ATSScore.model_validate(diff.get("score_before"))
        after = ATSScore.model_validate(diff.get("score_after"))
    except Exception:
        return None, None
    return before, after


async def _score_pair(
    profile: StructuredResume,
    tailored_resume: StructuredResume,
    requirements: JobRequirements,
) -> tuple[ATSScore, ATSScore]:
    return await anyio.to_thread.run_sync(
        lambda: (score_resume(profile, requirements), score_resume(tailored_resume, requirements))
    )


def _diff_summary(diff: dict | None) -> KitDiffSummary:
    if not diff:
        return KitDiffSummary()
    changes = diff.get("changes") or []
    stats = diff.get("stats") or {}
    discarded = diff.get("discarded_rewrites") or []
    bullet_rewrites = sum(
        1
        for change in changes
        if isinstance(change, dict) and change.get("bullet_ref") != "/skills"
    )
    skills_reordered = bool(stats.get("skills_reordered")) or any(
        isinstance(change, dict) and change.get("bullet_ref") == "/skills" for change in changes
    )
    return KitDiffSummary(
        changes=len(changes),
        bullet_rewrites=bullet_rewrites,
        skills_reordered=skills_reordered,
        discarded_rewrites=len(discarded),
        rewrite_candidates=int(stats.get("rewrite_candidates") or 0),
        rewrites_accepted=int(stats.get("rewrites_accepted") or bullet_rewrites),
        rewrites_discarded=int(stats.get("rewrites_discarded") or len(discarded)),
    )


async def _presigned_url(document: Document) -> str:
    return await anyio.to_thread.run_sync(storage.presigned_get_url, document.s3_key, 900)


async def _cover_letter_pdf_document(
    session: AsyncSession, version_id: uuid.UUID, cover_letter_id: uuid.UUID
) -> Document | None:
    """Latest rendered PDF for this specific cover letter (keyed by s3 path suffix)."""
    expected_suffix = f"/cover_letters/{cover_letter_id}.pdf"
    result = await session.execute(
        select(Document)
        .where(
            Document.resume_version_id == version_id,
            Document.kind == DocumentKind.cover_letter_pdf,
        )
        .order_by(Document.created_at.desc())
    )
    return next(
        (
            document
            for document in result.scalars().all()
            if document.s3_key.endswith(expected_suffix)
        ),
        None,
    )


async def _ensure_tailored_version(
    session: AsyncSession,
    job_target: JobTarget,
    profile_row: Profile,
    requirements: JobRequirements,
    *,
    force: bool,
    model: str | None = None,
) -> tuple[ResumeVersion, ATSScore, ATSScore, LLMUsage]:
    profile = StructuredResume.model_validate(profile_row.data)
    version = await _tailored_version(session, profile_row.id, job_target.id)
    if version is not None and not force:
        score_before, score_after = _scores_from_diff(version.diff)
        if score_before is not None and score_after is not None:
            if version.score_cache is None:
                version.score_cache = build_score_cache(job_target.id, score_after)
                await session.flush()
            return version, score_before, score_after, LLMUsage()
        tailored_resume = StructuredResume.model_validate(version.data)
        score_before, score_after = await _score_pair(profile, tailored_resume, requirements)
        version.diff = {
            **(version.diff or {}),
            "score_before": score_before.model_dump(mode="json"),
            "score_after": score_after.model_dump(mode="json"),
        }
        version.score_cache = build_score_cache(job_target.id, score_after)
        await session.flush()
        return version, score_before, score_after, LLMUsage()

    result = await tailor(profile, requirements, model=model)
    score_before, score_after = await _score_pair(profile, result.resume, requirements)
    diff = {
        "changes": [entry.model_dump(mode="json") for entry in result.diff],
        "stats": result.stats.model_dump(mode="json"),
        "discarded_rewrites": [
            rewrite.model_dump(mode="json") for rewrite in result.discarded_rewrites
        ],
        "score_before": score_before.model_dump(mode="json"),
        "score_after": score_after.model_dump(mode="json"),
    }
    if version is None:
        version = ResumeVersion(
            profile_id=profile_row.id,
            job_target_id=job_target.id,
            data=result.resume.model_dump(mode="json"),
            score_cache=build_score_cache(job_target.id, score_after),
            diff=diff,
            label=f"Tailored for {job_target.company or job_target.title or 'job target'}",
        )
        session.add(version)
    else:
        version.data = result.resume.model_dump(mode="json")
        version.score_cache = build_score_cache(job_target.id, score_after)
        version.diff = diff
        version.label = f"Tailored for {job_target.company or job_target.title or 'job target'}"
    await session.flush()
    return version, score_before, score_after, result.stats.usage


async def _ensure_resume_pdf(
    session: AsyncSession,
    version: ResumeVersion,
    *,
    force: bool,
    template: str | None = None,
) -> str:
    # A template switch must re-render even when a PDF already exists.
    template_changed = template is not None and template != version.template_id
    if force or template_changed:
        existing = None
    else:
        existing = await _document(session, version.id, DocumentKind.resume_pdf)
    if existing is not None:
        return await _presigned_url(existing)
    rendered = await render_version_document(
        session,
        version.id,
        RenderRequest(format="pdf", template=template),
    )
    return rendered.download_url


async def _ensure_cover_letter(
    session: AsyncSession,
    job_target: JobTarget,
    profile_row: Profile,
    version: ResumeVersion,
    requirements: JobRequirements,
    tone: Tone,
    *,
    force: bool,
    model: str | None = None,
) -> tuple[CoverLetter, LLMUsage]:
    existing = await _cover_letter(session, job_target.id, version.id, tone)
    if existing is not None and not force:
        return existing, LLMUsage()

    result = await generate_cover_letter(
        StructuredResume.model_validate(profile_row.data),
        requirements,
        job_target.raw_description,
        StructuredResume.model_validate(version.data),
        tone=tone,
        model=model,
    )

    if existing is None:
        existing = CoverLetter(
            job_target_id=job_target.id,
            resume_version_id=version.id,
            body_markdown=result.body_markdown,
            tone=CoverLetterTone(tone),
            word_count=result.word_count,
            claim_report=result.claim_report.model_dump(mode="json"),
        )
        session.add(existing)
    else:
        existing.body_markdown = result.body_markdown
        existing.word_count = result.word_count
        existing.claim_report = result.claim_report.model_dump(mode="json")
    await session.flush()
    return existing, result.usage


async def _ensure_cover_letter_pdf(
    session: AsyncSession,
    cover_letter: CoverLetter,
    version: ResumeVersion,
    *,
    force: bool,
) -> str:
    existing = None
    if not force:
        existing = await _cover_letter_pdf_document(session, version.id, cover_letter.id)
    if existing is not None:
        return await _presigned_url(existing)
    rendered = await render_cover_letter_document(
        session,
        cover_letter.id,
        RenderRequest(format="pdf"),
    )
    return rendered.download_url


async def create_or_get_kit(
    session: AsyncSession,
    job_target_id: uuid.UUID,
    payload: KitRequest,
    *,
    model: str | None = None,
) -> KitResult:
    job_target = await session.get(JobTarget, job_target_id)
    if job_target is None:
        raise NotFoundError(f"job target {job_target_id} not found")

    profile_row = await _canonical_profile(session, job_target.user_id)
    if profile_row is None:
        raise NotFoundError(f"user {job_target.user_id} has no canonical profile")

    usage = LLMUsage()
    requirements, extraction_usage = await _requirements_for_post(
        session,
        job_target,
        model=model,
    )
    usage += extraction_usage
    version, score_before, score_after, tailor_usage = await _ensure_tailored_version(
        session,
        job_target,
        profile_row,
        requirements,
        force=payload.force,
        model=model,
    )
    usage += tailor_usage
    resume_pdf_url = await _ensure_resume_pdf(
        session, version, force=payload.force, template=payload.template
    )
    cover_letter, cover_letter_usage = await _ensure_cover_letter(
        session,
        job_target,
        profile_row,
        version,
        requirements,
        payload.tone,
        force=payload.force,
        model=model,
    )
    usage += cover_letter_usage
    cover_letter_pdf_url = await _ensure_cover_letter_pdf(
        session,
        cover_letter,
        version,
        force=payload.force,
    )
    await session.commit()
    return KitResult(
        resume_version_id=version.id,
        score_before=score_before,
        score_after=score_after,
        resume_pdf_url=resume_pdf_url,
        cover_letter_id=cover_letter.id,
        cover_letter_pdf_url=cover_letter_pdf_url,
        diff_summary=_diff_summary(version.diff),
        usage=usage,
    )


async def get_existing_kit(session: AsyncSession, job_target_id: uuid.UUID) -> KitResult:
    job_target = await session.get(JobTarget, job_target_id)
    if job_target is None:
        raise NotFoundError(f"job target {job_target_id} not found")

    missing: list[str] = []
    profile_row = await _canonical_profile(session, job_target.user_id)
    if profile_row is None:
        missing.append("canonical_profile")
        raise KitMissingPiecesError(missing)

    if job_target.extracted_requirements is None:
        missing.append("requirements")
    version = await _tailored_version(session, profile_row.id, job_target.id)
    if version is None:
        missing.append("tailored_resume_version")
    resume_doc = None
    cover_letter = None
    cover_doc = None
    if version is not None:
        resume_doc = await _document(session, version.id, DocumentKind.resume_pdf)
        if resume_doc is None:
            missing.append("resume_pdf")
        cover_letter = await _cover_letter(session, job_target.id, version.id, "standard")
        if cover_letter is None:
            missing.append("cover_letter")
        else:
            cover_doc = await _cover_letter_pdf_document(session, version.id, cover_letter.id)
            if cover_doc is None:
                missing.append("cover_letter_pdf")

    if missing:
        raise KitMissingPiecesError(missing)

    assert version is not None
    assert resume_doc is not None
    assert cover_letter is not None
    assert cover_doc is not None
    assert job_target.extracted_requirements is not None

    score_before, score_after = _scores_from_diff(version.diff)
    if score_before is None or score_after is None:
        requirements = JobRequirements.model_validate(job_target.extracted_requirements)
        score_before, score_after = await _score_pair(
            StructuredResume.model_validate(profile_row.data),
            StructuredResume.model_validate(version.data),
            requirements,
        )

    return KitResult(
        resume_version_id=version.id,
        score_before=score_before,
        score_after=score_after,
        resume_pdf_url=await _presigned_url(resume_doc),
        cover_letter_id=cover_letter.id,
        cover_letter_pdf_url=await _presigned_url(cover_doc),
        diff_summary=_diff_summary(version.diff),
        usage=LLMUsage(),
    )


def _claim_summary(claim_report: dict | None) -> KitClaimSummary:
    report = claim_report or {}
    claims_checked = sum(
        len(report.get(key) or [])
        for key in ("proper_nouns_checked", "numbers_checked", "company_fact_sentences_checked")
    )
    return KitClaimSummary(
        passed=bool(report.get("passed")),
        claims_checked=claims_checked,
        violations=[str(violation) for violation in report.get("violations") or []],
    )


def _missing_terms(version: ResumeVersion, score_after: ATSScore | None) -> list[str]:
    if score_after is not None:
        return score_after.keyword_coverage.missing_terms
    score = (version.score_cache or {}).get("score")
    if isinstance(score, dict):
        try:
            return ATSScore.model_validate(score).keyword_coverage.missing_terms
        except Exception:
            return []
    return []


async def get_application_kit_detail(
    session: AsyncSession, application_id: uuid.UUID
) -> ApplicationKitDetail:
    """The kit view for one application row: exactly what went out, with download URLs."""
    application = await session.get(Application, application_id)
    if application is None:
        raise NotFoundError(f"application {application_id} not found")
    version = await session.get(ResumeVersion, application.resume_version_id)
    if version is None:
        raise NotFoundError(f"resume version {application.resume_version_id} not found")

    score_before, score_after = _scores_from_diff(version.diff)
    headline_after = (
        score_after.headline_score
        if score_after is not None
        else headline_from_cache(version.score_cache)
    )

    resume_pdf = await _document(session, version.id, DocumentKind.resume_pdf)
    resume_docx = await _document(session, version.id, DocumentKind.resume_docx)

    cover_result = await session.execute(
        select(CoverLetter)
        .where(
            CoverLetter.job_target_id == application.job_target_id,
            CoverLetter.resume_version_id == version.id,
        )
        .order_by(CoverLetter.created_at.desc())
    )
    cover = cover_result.scalars().first()
    cover_detail = None
    if cover is not None:
        cover_doc = await _cover_letter_pdf_document(session, version.id, cover.id)
        cover_detail = KitCoverLetterDetail(
            id=cover.id,
            tone=cover.tone.value,
            body_markdown=cover.body_markdown,
            word_count=cover.word_count,
            claims=_claim_summary(cover.claim_report),
            pdf_url=await _presigned_url(cover_doc) if cover_doc is not None else None,
        )

    followups_result = await session.execute(
        select(Followup)
        .where(Followup.application_id == application_id)
        .order_by(Followup.created_at.desc())
    )
    followups = [FollowupRead.model_validate(row) for row in followups_result.scalars().all()]

    return ApplicationKitDetail(
        application_id=application.id,
        resume_version=KitVersionDetail(
            id=version.id,
            label=version.label,
            template_id=version.template_id,
            created_at=version.created_at,
            score_before=score_before.headline_score if score_before is not None else None,
            score_after=headline_after,
            missing_terms=_missing_terms(version, score_after),
            pdf_url=await _presigned_url(resume_pdf) if resume_pdf is not None else None,
            docx_url=await _presigned_url(resume_docx) if resume_docx is not None else None,
        ),
        cover_letter=cover_detail,
        followups=followups,
    )
