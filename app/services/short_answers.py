"""Short-answer form-response generation, verification, and persistence.

Same evidence-pack + verify_prose discipline as cover letters (see CLAUDE.md),
with one extra guardrail: a short-answer question that actually asks for a fact
only the user knows — salary, work authorization, start date, relocation — is
refused, not generated. Those facts live in the AnswerProfile and must never be
guessed by the LLM, even if an ATS phrases them as a free-text question.
"""

import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.ats_fields import infer_short_answer_kind
from app.models import JobTarget, ResumeVersion, ShortAnswer
from app.models.short_answer import ShortAnswerKind, hash_question
from app.schemas.ats_fields import FieldSpec
from app.schemas.jd import JobRequirements
from app.schemas.llm import LLMUsage
from app.schemas.resume import StructuredResume
from app.schemas.short_answer import (
    ShortAnswerGenerationOutput,
    ShortAnswerRequest,
    ShortAnswerResult,
)
from app.services.claims import verify_prose
from app.services.errors import NeedsAnswerProfileError, NotFoundError, ProseVerificationError
from app.services.evidence import (
    EvidencePack,
    build_evidence_pack,
    evidence_pack_for_prompt,
    evidence_ref_violations,
    word_count,
)
from app.services.jd import extract_requirements
from app.services.llm import LLMOutputInvalidError, generate_structured

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You write factual, grounded answers to job-application short-answer questions
from a deliberately small evidence pack. The evidence pack is the only source
you may use.

Hard constraints:

- Answer the specific question asked. Be concrete; do not restate the whole
  resume.
- Every factual statement about the candidate must trace to an evidence_ref
  from a resume bullet or matched skill.
- Every factual statement about the company or role must trace to a JD snippet.
- Do not invent employers, titles, dates, tools, metrics, outcomes, team sizes,
  company praise, awards, funding, mutual connections, or personal backstory
  that is not in the evidence pack.
- Numbers are sacred: use only exact numeric strings from the evidence pack. Do
  not convert 8k to 8000.
- Never state facts that are personal and known only to the applicant: salary
  or compensation expectations, work authorization or visa/sponsorship status,
  start date or notice period, or relocation willingness. If the question asks
  for one of these, answer with the single word UNKNOWN.
- Do not leave bracketed placeholders like [COMPANY].
- Follow the length target in the user message.

Return body_markdown and claims_used. Each claims_used item must include the
statement and the exact evidence_ref that supports it.
"""

# Length scales to the kind of question. The "why" prompts are known shapes with
# a tight band; a custom question is open-ended, so the model estimates length
# from the question's own phrasing, hard-capped so no answer runs away.
_LENGTH_BOUNDS: dict[ShortAnswerKind, tuple[int, int]] = {
    ShortAnswerKind.why_company: (60, 120),
    ShortAnswerKind.why_role: (60, 120),
    ShortAnswerKind.custom: (40, 150),
}

_BRACKET_PLACEHOLDER_RE = re.compile(r"\[[A-Za-z0-9 _'/-]+\]")

# Deterministic guardrail: questions that are really asking for an AnswerProfile
# fact. Each pattern maps to the exact AnswerProfile field the UI should collect
# instead of generating prose. Order does not matter; first match wins.
_PERSONAL_DATA_CHECKS: list[tuple[str, re.Pattern[str]]] = [
    (
        "work_auth",
        re.compile(
            r"""\b(
                work\s+authoriz\w* | authoriz\w*\s+to\s+work | legally\s+authoriz\w* |
                right\s+to\s+work | work\s+permit | require\w*\s+(?:visa|sponsorship) |
                need\w*\s+(?:a\s+)?(?:visa|sponsorship) | sponsorship |
                visa\s+status | green\s+card | citizenship\s+status
            )\b""",
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        "salary_min",
        re.compile(
            r"""\b(
                salary | compensation | desired\s+pay | expected\s+pay |
                pay\s+expectation | comp\s+expectation | hourly\s+rate |
                rate\s+expectation | expected\s+rate | wage | remuneration
            )\b""",
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        "notice_period_days",
        re.compile(
            r"""\b(
                start\s+date | when\s+can\s+you\s+start | available\s+to\s+start |
                availability\s+to\s+start | notice\s+period | how\s+much\s+notice |
                earliest\s+(?:start|you\s+can\s+start) | when\s+are\s+you\s+available
            )\b""",
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        "relocation",
        re.compile(
            r"\b(relocat\w*|willing\s+to\s+move|open\s+to\s+moving)\b",
            re.IGNORECASE,
        ),
    ),
]


def detect_personal_data_field(question: str) -> str | None:
    """Return the AnswerProfile field a question is really asking for, or None."""
    for field, pattern in _PERSONAL_DATA_CHECKS:
        if pattern.search(question):
            return field
    return None


def _guard_personal_data(question: str) -> None:
    field = detect_personal_data_field(question)
    if field is not None:
        raise NeedsAnswerProfileError(field, question)


def _length_guidance(kind: ShortAnswerKind) -> str:
    low, high = _LENGTH_BOUNDS[kind]
    if kind is ShortAnswerKind.custom:
        return (
            f"Write between {low} and {high} words. Estimate the right length from the "
            "question itself: a yes/no or single-fact question should land near the low "
            f"end; an open 'tell us about a time...' question can run longer. Never "
            f"exceed {high} words."
        )
    return f"Write between {low} and {high} words."


def _structural_violations(body: str, kind: ShortAnswerKind) -> list[str]:
    violations: list[str] = []
    if not body.strip():
        return ["body_markdown is empty"]
    low, high = _LENGTH_BOUNDS[kind]
    count = word_count(body)
    if not low <= count <= high:
        violations.append(f"word count {count} outside {low}-{high} for {kind}")
    if _BRACKET_PLACEHOLDER_RE.search(body):
        violations.append("contains an unfilled bracketed placeholder")
    return violations


def _verification_violations(
    output: ShortAnswerGenerationOutput,
    pack: EvidencePack,
    resume_version: StructuredResume,
    raw_jd: str,
    kind: ShortAnswerKind,
) -> tuple[list[str], object]:
    claim_report = verify_prose(output.body_markdown, resume_version, raw_jd)
    violations = [
        *_structural_violations(output.body_markdown, kind),
        *evidence_ref_violations(output.claims_used, pack),
        *claim_report.violations,
    ]
    return violations, claim_report


async def _generate_once(
    pack: EvidencePack,
    question: str,
    kind: ShortAnswerKind,
    *,
    model: str | None,
    retry_violations: list[str] | None = None,
) -> tuple[ShortAnswerGenerationOutput, LLMUsage]:
    retry_context = ""
    if retry_violations:
        retry_context = (
            "\n\nThe previous draft failed verification. Fix these issues without "
            "adding new facts:\n" + "\n".join(f"- {violation}" for violation in retry_violations)
        )
    user_content = (
        f"Question kind: {kind}\n"
        f"Question: {question}\n"
        f"Length target: {_length_guidance(kind)}\n\n"
        f"Evidence pack:\n{evidence_pack_for_prompt(pack)}"
        f"{retry_context}"
    )
    output, usage = await generate_structured(
        ShortAnswerGenerationOutput,
        system=SYSTEM_PROMPT,
        user_content=user_content,
        model=model,
        max_tokens=2000,
    )
    return output, usage


async def generate_short_answer(
    job_target: JobTarget,
    resume_version: StructuredResume,
    question: str,
    question_kind: ShortAnswerKind,
    *,
    model: str | None = None,
) -> ShortAnswerResult:
    """Generate one grounded short answer, or refuse a personal-data question.

    ``job_target.extracted_requirements`` must already be populated (the
    orchestration wrapper guarantees it). Verification grounds the answer against
    the tailored ``resume_version`` and the JD, with regenerate-once-then-fail.
    """
    _guard_personal_data(question)  # raises NeedsAnswerProfileError before any LLM call

    requirements = JobRequirements.model_validate(job_target.extracted_requirements)
    raw_jd = job_target.raw_description
    pack = await build_evidence_pack(resume_version, requirements, raw_jd)

    usage = LLMUsage()
    last_output: ShortAnswerGenerationOutput | None = None
    last_claim_report = None
    last_violations: list[str] = []

    for attempt in range(2):
        output, item_usage = await _generate_once(
            pack,
            question,
            question_kind,
            model=model,
            retry_violations=last_violations if attempt else None,
        )
        usage += item_usage
        last_output = output
        violations, claim_report = _verification_violations(
            output, pack, resume_version, raw_jd, question_kind
        )
        last_claim_report = claim_report
        if not violations:
            return ShortAnswerResult(
                question=question,
                question_kind=question_kind,
                answer_markdown=output.body_markdown.strip(),
                word_count=word_count(output.body_markdown),
                claim_report=claim_report,
                usage=usage,
            )
        logger.warning("short answer verification failed: %s", "; ".join(violations))
        last_violations = violations

    assert last_output is not None
    assert last_claim_report is not None
    raise ProseVerificationError(
        "short answer failed verification after retry: " + "; ".join(last_violations)
    )


async def _latest_version_for_job(session: AsyncSession, job_target: JobTarget) -> ResumeVersion:
    result = await session.execute(
        select(ResumeVersion)
        .where(
            ResumeVersion.job_target_id == job_target.id,
            ResumeVersion.deleted_at.is_(None),
        )
        .order_by(ResumeVersion.created_at.desc())
    )
    version = result.scalars().first()
    if version is None:
        raise NotFoundError(
            f"no resume version found for job target {job_target.id}; generate a kit first"
        )
    return version


async def generate_short_answer_for_job(
    session: AsyncSession,
    job_target_id: uuid.UUID,
    payload: ShortAnswerRequest,
    *,
    model: str | None = None,
) -> ShortAnswerResult:
    """Generate and upsert a short answer for a job target.

    Idempotent by normalized question hash: regenerating the same question
    replaces its row instead of piling up duplicates.
    """
    job_target = await session.get(JobTarget, job_target_id)
    if job_target is None:
        raise NotFoundError(f"job target {job_target_id} not found")

    version = await _latest_version_for_job(session, job_target)

    if job_target.extracted_requirements is None:
        requirements, _ = await extract_requirements(job_target.raw_description, model=model)
        job_target.extracted_requirements = requirements.model_dump(mode="json")
        await session.flush()

    kind = payload.question_kind or infer_short_answer_kind(payload.question)
    resume_version = StructuredResume.model_validate(version.data)
    result = await generate_short_answer(
        job_target, resume_version, payload.question, kind, model=model
    )
    row = await _upsert_short_answer(session, job_target.id, payload.question, kind, result)
    await session.commit()
    await session.refresh(row)
    return result.model_copy(update={"id": row.id})


async def _upsert_short_answer(
    session: AsyncSession,
    job_target_id: uuid.UUID,
    question: str,
    kind: ShortAnswerKind,
    result: ShortAnswerResult,
) -> ShortAnswer:
    """Insert-or-replace a short answer row keyed by normalized question hash.

    Flushes but does not commit, so callers can batch several fields (the
    apply-kit) into one transaction.
    """
    question_hash = hash_question(question)
    existing = await session.execute(
        select(ShortAnswer).where(
            ShortAnswer.job_target_id == job_target_id,
            ShortAnswer.question_hash == question_hash,
        )
    )
    row = existing.scalar_one_or_none()
    claim_report_json = result.claim_report.model_dump(mode="json")
    if row is None:
        row = ShortAnswer(
            job_target_id=job_target_id,
            question=question,
            question_hash=question_hash,
            answer_markdown=result.answer_markdown,
            question_kind=kind,
            claim_report=claim_report_json,
        )
        session.add(row)
    else:
        row.question = question
        row.answer_markdown = result.answer_markdown
        row.question_kind = kind
        row.claim_report = claim_report_json
    await session.flush()
    return row


async def ensure_short_answer_field(
    session: AsyncSession,
    job_target: JobTarget,
    resume_version: StructuredResume,
    spec: FieldSpec,
    *,
    force: bool = False,
    model: str | None = None,
) -> tuple[ShortAnswer | None, str | None]:
    """Resolve one generated short-answer field for the apply-kit.

    Returns ``(row, None)`` on a cache hit or a successful generation, or
    ``(None, reason)`` if generation failed after its retry — the apply-kit
    surfaces the reason rather than dropping the field. Existing answers are
    reused unless ``force`` is set (the "polish one line" path).
    """
    assert spec.question_kind is not None, "only generated short-answer fields are ensurable"
    question_hash = hash_question(spec.label)
    existing = await session.execute(
        select(ShortAnswer).where(
            ShortAnswer.job_target_id == job_target.id,
            ShortAnswer.question_hash == question_hash,
        )
    )
    row = existing.scalar_one_or_none()
    if row is not None and not force:
        return row, None

    try:
        result = await generate_short_answer(
            job_target, resume_version, spec.label, spec.question_kind, model=model
        )
    except (ProseVerificationError, NeedsAnswerProfileError, LLMOutputInvalidError) as exc:
        return None, str(exc)

    row = await _upsert_short_answer(session, job_target.id, spec.label, spec.question_kind, result)
    return row, None


async def list_short_answers_for_job(
    session: AsyncSession, job_target_id: uuid.UUID
) -> list[ShortAnswer]:
    job_target = await session.get(JobTarget, job_target_id)
    if job_target is None:
        raise NotFoundError(f"job target {job_target_id} not found")
    result = await session.execute(
        select(ShortAnswer)
        .where(ShortAnswer.job_target_id == job_target_id)
        .order_by(ShortAnswer.created_at.desc())
    )
    return list(result.scalars().all())
