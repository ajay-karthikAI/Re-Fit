"""Follow-up email generation and persistence."""

from dataclasses import dataclass
from datetime import date, timedelta
import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application, Followup, FollowupKind, JobTarget, Profile, ResumeVersion
from app.schemas.followup import FollowupOutput, FollowupRequest, FollowupResult
from app.schemas.jd import JobRequirements
from app.schemas.llm import LLMUsage
from app.schemas.resume import StructuredResume
from app.services.claims import verify_prose
from app.services.evidence import (
    EvidencePack,
    build_evidence_pack as _build_evidence_pack,
    evidence_pack_for_prompt as _evidence_pack_for_prompt,
    guess_company_or_team as _guess_company_or_team,
    guess_title as _guess_title,
    word_count as _word_count,
)
from app.services.errors import ConflictError, NotFoundError, ProseVerificationError
from app.services.jd import extract_requirements
from app.services.llm import generate_structured

logger = logging.getLogger(__name__)

INTERVIEW_PLACEHOLDER = "[PERSONAL DETAIL FROM YOUR CONVERSATION]"

SYSTEM_PROMPT = """\
You write short, factual follow-up emails from a deliberately small evidence
pack. The evidence pack and application metadata are the only sources you may
use.

Hard constraints:

- Do not invent candidate experience, employers, titles, dates, tools, metrics,
  outcomes, company praise, mutual connections, or personal backstory.
- Every factual candidate statement must trace to a resume bullet or matched
  skill evidence_ref.
- Every factual company or role statement must trace to a JD snippet.
- Keep the subject plain and specific.
- For post_apply: write 80-120 words and reaffirm exactly one specific
  qualification from the evidence pack.
- For post_interview: write a thank-you referencing only the role and company.
  You do not know what was discussed. Do not invent interview details, names,
  topics, reactions, roadmap information, next steps, or team commentary. Include
  the literal placeholder [PERSONAL DETAIL FROM YOUR CONVERSATION] exactly once
  for the user to replace.
- For checkin: write 60-90 words, graceful and low-pressure.

Return subject, body_markdown, and claims_used. Each claims_used item must
include the statement and exact evidence_ref that supports it.
"""

_WORD_LIMITS: dict[FollowupKind, tuple[int, int]] = {
    FollowupKind.post_apply: (80, 120),
    FollowupKind.post_interview: (70, 120),
    FollowupKind.checkin: (60, 90),
}

_INTERVIEW_DETAIL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\byou mentioned\b",
        r"\byou shared\b",
        r"\bwe discussed\b",
        r"\bwe talked\b",
        r"\bour conversation about\b",
        r"\bi enjoyed hearing\b",
        r"\bi appreciated learning\b",
        r"\broadmap\b",
        r"\bnext steps\b",
        r"\bthe team is\b",
    ]
]


@dataclass(frozen=True)
class FollowupGenerationContext:
    application: Application
    profile: StructuredResume
    requirements: JobRequirements
    raw_jd: str
    resume_version: StructuredResume
    company: str | None = None
    title: str | None = None


def add_business_days(start: date, days: int) -> date:
    """Add business days, skipping weekends.

    Known limitation: holidays are intentionally ignored until we introduce a
    region-aware calendar.
    """
    if days < 0:
        raise ValueError("business-day offset must be non-negative")
    current = start
    remaining = days
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def _source_jd(context: FollowupGenerationContext) -> str:
    metadata = []
    if context.company:
        metadata.append(f"Company: {context.company}")
    if context.title:
        metadata.append(f"Role: {context.title}")
    metadata.append(context.raw_jd)
    return "\n".join(metadata)


def _send_after(application: Application, kind: FollowupKind) -> date | None:
    if application.applied_at is None:
        return None
    base = application.applied_at.date()
    if kind == FollowupKind.post_apply:
        return add_business_days(base, 5)
    if kind == FollowupKind.post_interview:
        return base + timedelta(days=1)
    return add_business_days(base, 10)


def _company_or_team(context: FollowupGenerationContext) -> str:
    if context.company:
        return context.company
    return _guess_company_or_team(_source_jd(context))


def _title(context: FollowupGenerationContext) -> str | None:
    if context.title:
        return context.title
    return _guess_title(_source_jd(context))


def _kind_rules(kind: FollowupKind) -> str:
    low, high = _WORD_LIMITS[kind]
    if kind == FollowupKind.post_apply:
        return (
            f"Kind: post_apply\nWord count: {low}-{high} words.\n"
            "Reaffirm one specific qualification, and only one, using evidence_refs."
        )
    if kind == FollowupKind.post_interview:
        return (
            f"Kind: post_interview\nWord count: {low}-{high} words.\n"
            f"Include {INTERVIEW_PLACEHOLDER} exactly once. Do not invent or imply "
            "anything specific from the interview conversation."
        )
    return (
        f"Kind: checkin\nWord count: {low}-{high} words.\n"
        "Keep it graceful, low-pressure, and concise."
    )


def _evidence_ref_violations(output: FollowupOutput, pack: EvidencePack) -> list[str]:
    if not output.claims_used:
        return ["claims_used is empty"]
    valid_refs = pack.refs
    return [
        f"claim uses unknown evidence_ref {claim.evidence_ref}"
        for claim in output.claims_used
        if claim.evidence_ref not in valid_refs
    ]


def _structural_violations(output: FollowupOutput, kind: FollowupKind) -> list[str]:
    violations: list[str] = []
    subject = output.subject.strip()
    body = output.body_markdown.strip()
    if not subject:
        violations.append("subject is empty")
    if not body:
        violations.append("body_markdown is empty")

    low, high = _WORD_LIMITS[kind]
    count = _word_count(body)
    if not low <= count <= high:
        violations.append(f"word count {count} outside {low}-{high}")

    if kind == FollowupKind.post_interview:
        placeholder_count = body.count(INTERVIEW_PLACEHOLDER)
        if placeholder_count != 1:
            violations.append(
                f"expected {INTERVIEW_PLACEHOLDER} exactly once; found {placeholder_count}"
            )
        body_without_placeholder = body.replace(INTERVIEW_PLACEHOLDER, " ")
        for pattern in _INTERVIEW_DETAIL_PATTERNS:
            if pattern.search(body_without_placeholder):
                violations.append(f"possible invented interview detail: {pattern.pattern}")
    return violations


def _verification_violations(
    output: FollowupOutput,
    kind: FollowupKind,
    pack: EvidencePack,
    context: FollowupGenerationContext,
) -> tuple[list[str], object]:
    source_jd = _source_jd(context)
    claim_report = verify_prose(
        f"{output.subject}\n\n{output.body_markdown}",
        context.profile,
        source_jd,
    )
    violations = [
        *_structural_violations(output, kind),
        *_evidence_ref_violations(output, pack),
        *claim_report.violations,
    ]
    return violations, claim_report


async def _generate_once(
    pack: EvidencePack,
    context: FollowupGenerationContext,
    kind: FollowupKind,
    *,
    model: str | None,
    retry_violations: list[str] | None = None,
) -> tuple[FollowupOutput, LLMUsage]:
    retry_context = ""
    if retry_violations:
        retry_context = (
            "\n\nThe previous draft failed verification. Fix these issues without "
            "adding new facts:\n" + "\n".join(f"- {violation}" for violation in retry_violations)
        )
    user_content = (
        f"{_kind_rules(kind)}\n\n"
        f"Company/team: {_company_or_team(context)}\n"
        f"Role title: {_title(context) or 'unknown'}\n\n"
        f"Evidence pack:\n{_evidence_pack_for_prompt(pack)}"
        f"{retry_context}"
    )
    output, usage = await generate_structured(
        FollowupOutput,
        system=SYSTEM_PROMPT,
        user_content=user_content,
        model=model,
        max_tokens=1600,
    )
    return output, usage


async def generate_followup(
    application: FollowupGenerationContext,
    kind: FollowupKind | str,
    *,
    model: str | None = None,
) -> FollowupResult:
    kind = FollowupKind(kind)
    if application.application.applied_at is None:
        raise ConflictError("application applied_at is required before generating followups")

    source_jd = _source_jd(application)
    pack = await _build_evidence_pack(
        application.resume_version,
        application.requirements,
        source_jd,
    )
    usage = LLMUsage()
    last_violations: list[str] = []
    last_output: FollowupOutput | None = None
    last_claim_report = None

    for attempt in range(2):
        output, item_usage = await _generate_once(
            pack,
            application,
            kind,
            model=model,
            retry_violations=last_violations if attempt else None,
        )
        usage += item_usage
        last_output = output
        violations, claim_report = _verification_violations(output, kind, pack, application)
        last_claim_report = claim_report
        if not violations:
            return FollowupResult(
                kind=kind,
                subject=output.subject.strip(),
                body_markdown=output.body_markdown.strip(),
                send_after=_send_after(application.application, kind),
                word_count=_word_count(output.body_markdown),
                claim_report=claim_report,
                usage=usage,
            )
        logger.warning("followup verification failed: %s", "; ".join(violations))
        last_violations = violations

    assert last_output is not None
    assert last_claim_report is not None
    raise ProseVerificationError(
        "followup failed verification after retry: " + "; ".join(last_violations)
    )


async def _followup_context(
    session: AsyncSession,
    application_id: uuid.UUID,
    *,
    model: str | None = None,
) -> FollowupGenerationContext:
    application = await session.get(Application, application_id)
    if application is None:
        raise NotFoundError(f"application {application_id} not found")

    job_target = await session.get(JobTarget, application.job_target_id)
    if job_target is None:
        raise NotFoundError(f"job target {application.job_target_id} not found")

    version = await session.get(ResumeVersion, application.resume_version_id)
    if version is None:
        raise NotFoundError(f"resume version {application.resume_version_id} not found")

    profile = await session.get(Profile, version.profile_id)
    if profile is None or profile.user_id != application.user_id:
        raise NotFoundError("application resume version does not belong to this user")

    if job_target.extracted_requirements is None:
        requirements, _ = await extract_requirements(job_target.raw_description, model=model)
        job_target.extracted_requirements = requirements.model_dump(mode="json")
        await session.flush()
    else:
        requirements = JobRequirements.model_validate(job_target.extracted_requirements)

    return FollowupGenerationContext(
        application=application,
        profile=StructuredResume.model_validate(profile.data),
        requirements=requirements,
        raw_jd=job_target.raw_description,
        resume_version=StructuredResume.model_validate(version.data),
        company=job_target.company,
        title=job_target.title,
    )


async def create_followup_for_application(
    session: AsyncSession,
    application_id: uuid.UUID,
    payload: FollowupRequest,
    *,
    model: str | None = None,
) -> FollowupResult:
    context = await _followup_context(session, application_id, model=model)
    result = await generate_followup(context, payload.kind, model=model)
    row = Followup(
        application_id=application_id,
        kind=payload.kind,
        subject=result.subject,
        body_markdown=result.body_markdown,
        send_after=result.send_after,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return result.model_copy(update={"id": row.id, "application_id": application_id})


async def list_followups_for_application(
    session: AsyncSession, application_id: uuid.UUID
) -> list[Followup]:
    application = await session.get(Application, application_id)
    if application is None:
        raise NotFoundError(f"application {application_id} not found")

    result = await session.execute(
        select(Followup)
        .where(Followup.application_id == application_id)
        .order_by(Followup.created_at.desc())
    )
    return list(result.scalars().all())
