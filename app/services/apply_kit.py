"""ApplyKit composition — the screen that IS the product for this phase.

GET assembles one payload: the ATS field plan with generated short answers
auto-resolved inline, the resume/cover-letter documents (rendered if needed),
the answer-profile gaps only the user can fill, and a checklist ordered to the
real form's physical field order. Viewing never creates an Application — that is
an explicit, separate ``track`` action.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.ats_fields import FIELD_TAXONOMY, build_field_plan
from app.models import AnswerProfile, JobTarget, Profile, ResumeVersion
from app.schemas.apply_kit import (
    AnswerProfileGap,
    ApplyKit,
    ApplyKitDocument,
    ChecklistAction,
    ChecklistStep,
)
from app.schemas.ats_fields import FieldPlanItem, FieldSpec
from app.schemas.kit import KitRequest
from app.schemas.resume import StructuredResume
from app.services import kit as kit_service
from app.services import short_answers
from app.services.errors import NotFoundError

# Section + physical action for each field, so the checklist reads like the real
# form. Keys not listed fall back by source (see _section_and_action).
_CONTACT_KEYS = {"name", "email", "phone", "linkedin_url", "github_url", "portfolio_url"}
_UPLOAD_KEYS = {"resume_upload", "cover_letter_upload"}
_SELECT_KEYS = {"work_authorization", "sponsorship", "relocation", "eeo"}


def _section_and_action(spec: FieldSpec) -> tuple[str, ChecklistAction]:
    if spec.key in _UPLOAD_KEYS:
        return "Documents", "upload"
    if spec.key in _CONTACT_KEYS:
        return "Contact", "copy"
    if spec.source == "answer_profile":
        return "Screening questions", "select" if spec.key in _SELECT_KEYS else "copy"
    if spec.source == "generated":  # a short-answer block
        return "Short answers", "copy"
    if spec.source == "manual_only":
        return "Voluntary self-ID", "select"
    return "Other", "copy"


async def _canonical_profile(session: AsyncSession, user_id: uuid.UUID) -> Profile | None:
    result = await session.execute(
        select(Profile).where(Profile.user_id == user_id, Profile.is_canonical)
    )
    return result.scalar_one_or_none()


async def _answer_profile(session: AsyncSession, user_id: uuid.UUID) -> AnswerProfile | None:
    result = await session.execute(select(AnswerProfile).where(AnswerProfile.user_id == user_id))
    return result.scalar_one_or_none()


def _answer_profile_gaps(items: list[FieldPlanItem]) -> list[AnswerProfileGap]:
    gaps: list[AnswerProfileGap] = []
    for item in items:
        spec = item.field_spec
        if spec.source == "answer_profile" and item.status == "needs_user_input":
            column = spec.mapped_from.split(".", 1)[1] if spec.mapped_from else spec.key
            gaps.append(
                AnswerProfileGap(
                    field=column,
                    label=spec.label,
                    link_target=f"/answer-profile?field={column}",
                )
            )
    return gaps


def _build_checklist(source_ats: str, resolved: list[FieldPlanItem]) -> list[ChecklistStep]:
    """Steps follow the taxonomy's declared field order — the physical order of
    the real form — which is what makes the "under 3 minutes" flow real."""
    by_key = {item.field_spec.key: item for item in resolved}
    steps: list[ChecklistStep] = []
    blocking = False
    for order, spec in enumerate(FIELD_TAXONOMY.get(source_ats, []), start=1):
        item = by_key[spec.key]
        section, action = _section_and_action(spec)
        steps.append(
            ChecklistStep(
                order=order,
                section=section,
                field_key=spec.key,
                label=spec.label,
                action=action,
                status=item.status,
            )
        )
        if item.status in ("needs_user_input", "error"):
            blocking = True
    steps.append(
        ChecklistStep(
            order=len(steps) + 1,
            section="Submit",
            field_key=None,
            label="Review and submit the application",
            action="submit",
            status="needs_user_input" if blocking else "ready",
        )
    )
    return steps


async def assemble_apply_kit(
    session: AsyncSession,
    job_target_id: uuid.UUID,
    *,
    force_field: str | None = None,
    model: str | None = None,
) -> ApplyKit:
    """Compose the full apply-kit, generating any missing pieces inline.

    Slow on the first call for a job target (it ensures the tailored resume,
    cover letter, renders, and every generated short answer); cheap afterward
    because each piece is cached. ``force_field`` regenerates exactly one
    short-answer field and leaves its siblings on their cached values.
    """
    job_target = await session.get(JobTarget, job_target_id)
    if job_target is None:
        raise NotFoundError(f"job target {job_target_id} not found")

    # Ensure the base kit exists: tailored version, resume PDF, cover letter, its PDF.
    kit_result = await kit_service.create_or_get_kit(
        session, job_target_id, KitRequest(), model=model
    )

    profile_row = await _canonical_profile(session, job_target.user_id)
    assert profile_row is not None  # create_or_get_kit would have raised otherwise
    answer_profile = await _answer_profile(session, job_target.user_id)
    version = await session.get(ResumeVersion, kit_result.resume_version_id)
    assert version is not None
    resume_data = StructuredResume.model_validate(version.data)
    profile_resume = StructuredResume.model_validate(profile_row.data)

    documents = [
        ApplyKitDocument(
            key="resume_pdf",
            label="Tailored resume (PDF)",
            download_url=kit_result.resume_pdf_url,
            ready=True,
        ),
        ApplyKitDocument(
            key="cover_letter_pdf",
            label="Cover letter (PDF)",
            download_url=kit_result.cover_letter_pdf_url,
            ready=True,
        ),
    ]

    base_plan = build_field_plan(job_target, answer_profile, profile_resume)
    resolved: list[FieldPlanItem] = []
    for item in base_plan:
        spec = item.field_spec
        if item.status != "needs_generation":
            resolved.append(item)
            continue
        if spec.question_kind is None:
            # A generated document upload (resume / cover letter) — the file is
            # ready in `documents`; point the field at it.
            resolved.append(
                FieldPlanItem(field_spec=spec, resolved_value=spec.label, status="ready")
            )
            continue
        row, error = await short_answers.ensure_short_answer_field(
            session,
            job_target,
            resume_data,
            spec,
            force=(spec.key == force_field),
            model=model,
        )
        if error is not None:
            resolved.append(
                FieldPlanItem(field_spec=spec, resolved_value=None, status="error", error=error)
            )
        else:
            assert row is not None
            resolved.append(
                FieldPlanItem(field_spec=spec, resolved_value=row.answer_markdown, status="ready")
            )

    await session.commit()

    return ApplyKit(
        job_target_id=job_target.id,
        source_ats=job_target.source_ats,
        source_url=job_target.source_url,
        field_plan=resolved,
        documents=documents,
        answer_profile_gaps=_answer_profile_gaps(resolved),
        checklist=_build_checklist(job_target.source_ats, resolved),
    )


async def regenerate_apply_kit_field(
    session: AsyncSession,
    job_target_id: uuid.UUID,
    field_key: str,
    *,
    model: str | None = None,
) -> ApplyKit:
    """Regenerate one short-answer field, leaving every sibling on its cached value."""
    job_target = await session.get(JobTarget, job_target_id)
    if job_target is None:
        raise NotFoundError(f"job target {job_target_id} not found")

    regenerable = {
        spec.key
        for spec in FIELD_TAXONOMY.get(job_target.source_ats, [])
        if spec.source == "generated" and spec.question_kind is not None
    }
    if field_key not in regenerable:
        raise NotFoundError(
            f"field {field_key!r} is not a regenerable short-answer field for this job target"
        )
    return await assemble_apply_kit(session, job_target_id, force_field=field_key, model=model)
