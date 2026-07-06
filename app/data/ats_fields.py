"""Encoded field taxonomies for the ATSs we target.

The set of application-form fields each of these ATSs presents is finite and
stable, so we encode it directly here rather than re-deriving "what goes in the
kit" per job. This makes ``build_field_plan`` a deterministic lookup + resolve.

``FIELD_TAXONOMY`` holds the *fixed* fields every posting on an ATS shows.
Per-posting *custom* questions are dynamic (they come from the individual job),
so they are not baked in here; ``custom_question_spec`` + ``infer_short_answer_kind``
build FieldSpecs for them on demand. That is the "generated on demand" path for
Ashby's ordered custom questions and Greenhouse's 0-3 custom slots.

No LLM and no I/O in this module — it is pure reference data and orchestration.
"""

import re
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from app.models.short_answer import ShortAnswerKind
from app.schemas.ats_fields import ATSName, FieldPlanItem, FieldSpec

if TYPE_CHECKING:
    from app.models import AnswerProfile, JobTarget
    from app.schemas.resume import StructuredResume

# --- fixed field taxonomies -------------------------------------------------

# Contact fields resolved straight from the user's canonical resume profile.
_NAME = FieldSpec(
    key="name",
    label="Full name",
    source="profile",
    mapped_from="profile.contact.full_name",
)
_EMAIL = FieldSpec(
    key="email",
    label="Email",
    source="profile",
    mapped_from="profile.contact.email",
)
_PHONE = FieldSpec(
    key="phone",
    label="Phone",
    source="profile",
    mapped_from="profile.contact.phone",
)
_LINKEDIN = FieldSpec(
    key="linkedin_url",
    label="LinkedIn URL",
    source="profile",
    mapped_from="profile.contact.linkedin_url",
)
_GITHUB = FieldSpec(
    key="github_url",
    label="GitHub URL",
    source="profile",
    mapped_from="profile.contact.github_url",
)
_PORTFOLIO = FieldSpec(
    key="portfolio_url",
    label="Portfolio URL",
    source="profile",
    mapped_from="profile.contact.portfolio_url",
)

# Documents refit renders for the kit and the user attaches.
_RESUME_UPLOAD = FieldSpec(
    key="resume_upload",
    label="Resume",
    source="generated",
    notes="Attach the tailored resume PDF from the application kit.",
)
_COVER_LETTER_UPLOAD = FieldSpec(
    key="cover_letter_upload",
    label="Cover letter",
    source="generated",
    notes="Attach the generated cover letter PDF from the application kit.",
)

# Answer-profile-backed facts.
_WORK_AUTH = FieldSpec(
    key="work_authorization",
    label="Are you authorized to work in this location?",
    source="answer_profile",
    mapped_from="answer_profile.work_auth",
)
_SPONSORSHIP = FieldSpec(
    key="sponsorship",
    label="Will you now or in the future require sponsorship?",
    source="answer_profile",
    mapped_from="answer_profile.sponsorship_needed",
)
_RELOCATION = FieldSpec(
    key="relocation",
    label="Are you willing to relocate?",
    source="answer_profile",
    mapped_from="answer_profile.relocation",
)
_DESIRED_SALARY = FieldSpec(
    key="desired_salary",
    label="Desired salary",
    source="answer_profile",
    mapped_from="answer_profile.salary_min",
    notes="Rendered as the salary_min-salary_max range from the answer profile.",
)
_HOW_DID_YOU_HEAR = FieldSpec(
    key="how_did_you_hear",
    label="How did you hear about us?",
    source="answer_profile",
    mapped_from="answer_profile.referral_source_default",
)

# Generated short-answer blocks (fixed, known prompts).
_WHY_COMPANY = FieldSpec(
    key="why_company",
    label="Why do you want to work here?",
    source="generated",
    question_kind=ShortAnswerKind.why_company,
)
_WHY_ROLE_ADDITIONAL = FieldSpec(
    key="additional_information",
    label="Additional information",
    source="generated",
    question_kind=ShortAnswerKind.why_role,
    notes="Lever's free-text field; filled with a general 'why this role' block.",
)

# EEO / self-ID: never auto-filled. Always the user's own click.
_EEO = FieldSpec(
    key="eeo",
    label="EEO / voluntary self-identification",
    source="manual_only",
    notes="Never auto-filled — always the applicant's own selection.",
)


FIELD_TAXONOMY: dict[str, list[FieldSpec]] = {
    # Greenhouse: the classic long form.
    "greenhouse": [
        _NAME,
        _EMAIL,
        _PHONE,
        _RESUME_UPLOAD,
        _COVER_LETTER_UPLOAD,
        _LINKEDIN,
        _WORK_AUTH,
        _SPONSORSHIP,
        _WHY_COMPANY,
        _RELOCATION,
        _DESIRED_SALARY,
        _HOW_DID_YOU_HEAR,
        _EEO,
    ],
    # Lever: resume + a single free-text "additional information" + urls[].
    "lever": [
        _NAME,
        _EMAIL,
        _PHONE,
        _RESUME_UPLOAD,
        _LINKEDIN,
        _GITHUB,
        _PORTFOLIO,
        _WHY_ROLE_ADDITIONAL,
        _EEO,
    ],
    # Ashby: lean fixed section; the meat is the ordered custom questions, which
    # are dynamic (see custom_question_spec / infer_short_answer_kind).
    "ashby": [
        _NAME,
        _EMAIL,
        _RESUME_UPLOAD,
        _LINKEDIN,
        _WORK_AUTH,
        _SPONSORSHIP,
        _EEO,
    ],
    "unknown": [],
}


# --- ATS detection ----------------------------------------------------------

_ATS_BY_HOST_SUFFIX: tuple[tuple[str, ATSName], ...] = (
    ("greenhouse.io", "greenhouse"),
    ("lever.co", "lever"),
    ("ashbyhq.com", "ashby"),
)


def detect_ats(source_url: str | None) -> ATSName:
    """Map a job posting URL to its ATS by hostname.

    Deliberately conservative: a company on a custom domain (e.g.
    ``careers.acme.com``) that merely *embeds* an ATS reads as ``unknown`` —
    we only claim an ATS when the canonical apply host says so.
    """
    if not source_url:
        return "unknown"
    raw = source_url.strip()
    # Add a scheme-less netloc marker so urlparse finds the host even when the
    # caller passed a bare "boards.greenhouse.io/acme/jobs/1".
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    host = (parsed.hostname or "").lower()
    for suffix, ats in _ATS_BY_HOST_SUFFIX:
        if host == suffix or host.endswith(f".{suffix}"):
            return ats
    return "unknown"


# --- dynamic custom questions ----------------------------------------------

_WHY = re.compile(r"\bwhy\b")
_COMPANY_HINT = re.compile(r"\b(company|us|here)\b")
_ROLE_HINT = re.compile(r"\b(role|position)\b")


def infer_short_answer_kind(question_text: str) -> ShortAnswerKind:
    """Classify a free-form ATS question into a short-answer kind by keyword.

    "why" + company/us/here -> why_company; "why" + role/position -> why_role;
    everything else -> custom.
    """
    q = question_text.lower()
    if _WHY.search(q):
        if _COMPANY_HINT.search(q):
            return ShortAnswerKind.why_company
        if _ROLE_HINT.search(q):
            return ShortAnswerKind.why_role
    return ShortAnswerKind.custom


def custom_question_spec(question_text: str, index: int) -> FieldSpec:
    """Build a generated-on-demand FieldSpec for a posting's custom question."""
    return FieldSpec(
        key=f"custom_{index}",
        label=question_text,
        source="generated",
        question_kind=infer_short_answer_kind(question_text),
        notes="Custom question from the job posting; generated on demand.",
    )


# --- field plan -------------------------------------------------------------


def _format_salary(answer_profile: "AnswerProfile") -> str | None:
    low = answer_profile.salary_min
    high = answer_profile.salary_max
    if low is None and high is None:
        return None
    currency = answer_profile.salary_currency
    unit = str(answer_profile.salary_type)
    if low is not None and high is not None:
        amount = f"{low:,}-{high:,}"
    else:
        amount = f"{low:,}" if low is not None else f"{high:,}"
    return f"{amount} {currency} ({unit})"


def _stringify(value: object) -> str:
    # bool must be checked before anything else: it is a valid, present answer.
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _resolve_answer_profile(spec: FieldSpec, answer_profile: "AnswerProfile | None") -> str | None:
    if answer_profile is None:
        return None
    if spec.key == "desired_salary":
        return _format_salary(answer_profile)
    assert spec.mapped_from is not None
    attr = spec.mapped_from.split(".", 1)[1]
    value = getattr(answer_profile, attr, None)
    return None if value is None else _stringify(value)


def _resolve_profile(spec: FieldSpec, profile: "StructuredResume | None") -> str | None:
    if profile is None or spec.mapped_from is None:
        return None
    # Paths are "profile.<attr>.<attr>...": walk everything after the root.
    obj: object = profile
    for part in spec.mapped_from.split(".")[1:]:
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return _stringify(obj)


def build_field_plan(
    job_target: "JobTarget",
    answer_profile: "AnswerProfile | None" = None,
    profile: "StructuredResume | None" = None,
) -> list[FieldPlanItem]:
    """Resolve the ATS's field taxonomy against a user's answer profile and resume.

    Pure orchestration — no LLM, no DB. Answer-profile and profile fields are
    resolved directly; generated fields are flagged for the next generation
    step; missing answer-profile fields are flagged ``needs_user_input`` so the
    UI can point the user at the exact field (``mapped_from``) to go fill in.
    """
    plan: list[FieldPlanItem] = []
    for spec in FIELD_TAXONOMY.get(job_target.source_ats, []):
        if spec.source == "generated":
            plan.append(
                FieldPlanItem(field_spec=spec, resolved_value=None, status="needs_generation")
            )
        elif spec.source == "manual_only":
            plan.append(FieldPlanItem(field_spec=spec, resolved_value=None, status="manual_only"))
        else:
            if spec.source == "answer_profile":
                value = _resolve_answer_profile(spec, answer_profile)
            else:  # "profile"
                value = _resolve_profile(spec, profile)
            status = "ready" if value is not None else "needs_user_input"
            plan.append(FieldPlanItem(field_spec=spec, resolved_value=value, status=status))
    return plan
