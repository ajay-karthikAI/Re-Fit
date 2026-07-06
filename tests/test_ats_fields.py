"""ATS field taxonomy: detection, kind inference, and the resolved field plan."""

from typing import Any

import pytest

from app.data.ats_fields import (
    build_field_plan,
    detect_ats,
    infer_short_answer_kind,
)
from app.models import AnswerProfile, JobTarget
from app.models.short_answer import ShortAnswerKind
from app.schemas.resume import StructuredResume

# The three answer-profile-backed fields that gate an application form.
_AUTH_FIELD_KEYS = {"work_authorization", "sponsorship", "relocation"}

RESUME_DICT: dict[str, Any] = {
    "contact": {
        "full_name": "Sam Okafor",
        "email": "sam.okafor@example.com",
        "phone": "(555) 019-4452",
        "location": "Chicago, IL",
        "linkedin_url": "https://www.linkedin.com/in/sam",
    },
    "summary": "Senior backend engineer.",
    "experience": [],
    "education": [],
    "skills": [],
    "projects": [],
}


def _full_answer_profile() -> AnswerProfile:
    return AnswerProfile(
        work_auth="citizen",
        sponsorship_needed=False,
        relocation="case_by_case",
        salary_min=140000,
        salary_max=170000,
        salary_currency="USD",
        salary_type="annual",
        referral_source_default="Company careers page",
    )


def _job_target(source_ats: str) -> JobTarget:
    # Transient, never flushed — build_field_plan is pure and only reads source_ats.
    return JobTarget(
        user_id=None,
        raw_description="A great backend role.",
        source_ats=source_ats,
    )


# --- detect_ats -------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://boards.greenhouse.io/acme/jobs/4567890", "greenhouse"),
        ("https://job-boards.greenhouse.io/acme/jobs/1", "greenhouse"),
        ("https://jobs.lever.co/acme/1a2b3c4d-5e6f", "lever"),
        ("https://jobs.ashbyhq.com/acme/abcd-1234", "ashby"),
        ("boards.greenhouse.io/acme/jobs/9", "greenhouse"),  # scheme-less
        ("https://JOBS.LEVER.CO/Acme/1", "lever"),  # case-insensitive host
        # Custom-domain edge case: a company careers page that may embed an ATS
        # but does not advertise it in the host -> unknown, deliberately.
        ("https://careers.acme.com/job/senior-backend-123", "unknown"),
        ("https://www.notlever.com/jobs/1", "unknown"),  # must not match on substring
        (None, "unknown"),
        ("", "unknown"),
    ],
)
def test_detect_ats(url: str | None, expected: str) -> None:
    assert detect_ats(url) == expected


# --- infer_short_answer_kind ------------------------------------------------


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Why do you want to work at our company?", ShortAnswerKind.why_company),
        ("Why us?", ShortAnswerKind.why_company),
        ("Why are you interested in this role?", ShortAnswerKind.why_role),
        ("Why is this position a fit for you?", ShortAnswerKind.why_role),
        ("Describe a hard technical problem you solved.", ShortAnswerKind.custom),
        # "why" absent -> custom even with a company word present.
        ("What do you know about our company?", ShortAnswerKind.custom),
    ],
)
def test_infer_short_answer_kind(question: str, expected: ShortAnswerKind) -> None:
    assert infer_short_answer_kind(question) == expected


# --- build_field_plan -------------------------------------------------------


def test_build_field_plan_full_profile_has_no_auth_needs_user_input() -> None:
    profile = StructuredResume.model_validate(RESUME_DICT)
    plan = build_field_plan(_job_target("greenhouse"), _full_answer_profile(), profile)

    by_key = {item.field_spec.key: item for item in plan}
    # The three gating answer-profile fields all resolve to "ready".
    for key in _AUTH_FIELD_KEYS:
        assert by_key[key].status == "ready", key
        assert by_key[key].resolved_value is not None

    # Nothing that is answer-profile-backed is flagged for user input.
    ap_needs_input = [
        item
        for item in plan
        if item.field_spec.source == "answer_profile" and item.status == "needs_user_input"
    ]
    assert ap_needs_input == []

    # sponsorship_needed=False is a real, present answer (not "missing").
    assert by_key["sponsorship"].resolved_value == "No"
    # Multi-field salary formatting.
    assert by_key["desired_salary"].resolved_value == "140,000-170,000 USD (annual)"
    # Generated + manual_only fields keep their non-resolving statuses.
    assert by_key["why_company"].status == "needs_generation"
    assert by_key["eeo"].status == "manual_only"
    # Profile-backed contact field resolves from the resume.
    assert by_key["name"].resolved_value == "Sam Okafor"


def test_build_field_plan_empty_profile_flags_auth_fields() -> None:
    profile = StructuredResume.model_validate(RESUME_DICT)
    plan = build_field_plan(_job_target("greenhouse"), answer_profile=None, profile=profile)

    by_key = {item.field_spec.key: item for item in plan}
    for key in _AUTH_FIELD_KEYS:
        item = by_key[key]
        assert item.status == "needs_user_input", key
        assert item.resolved_value is None
        # The UI gets the exact field to go fill in.
        assert item.field_spec.mapped_from is not None
        assert item.field_spec.mapped_from.startswith("answer_profile.")

    # Profile-backed fields still resolve even with no answer profile.
    assert by_key["email"].status == "ready"
    # Generated/manual statuses are independent of the answer profile.
    assert by_key["why_company"].status == "needs_generation"
    assert by_key["eeo"].status == "manual_only"


def test_build_field_plan_unknown_ats_is_empty() -> None:
    plan = build_field_plan(_job_target("unknown"), _full_answer_profile())
    assert plan == []


def test_build_field_plan_lever_uses_generated_additional_info() -> None:
    plan = build_field_plan(_job_target("lever"), _full_answer_profile())
    by_key = {item.field_spec.key: item for item in plan}
    additional = by_key["additional_information"]
    assert additional.status == "needs_generation"
    assert additional.field_spec.question_kind == ShortAnswerKind.why_role
