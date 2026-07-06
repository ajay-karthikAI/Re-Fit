"""Short-answer generation: the personal-data guardrail, fabrication rejection,
and length scaling. The LLM call itself is stubbed; everything around it — the
guardrail, evidence-ref check, verify_prose gate, and length bounds — is real.
"""

from typing import Any

import pytest
from pytest import MonkeyPatch

from app.models import JobTarget
from app.models.short_answer import ShortAnswerKind
from app.schemas.cover_letter import ClaimUsed
from app.schemas.jd import JobRequirements, RequirementItem
from app.schemas.llm import LLMUsage
from app.schemas.resume import StructuredResume
from app.schemas.short_answer import ShortAnswerGenerationOutput
from app.services import short_answers as sa
from app.services.errors import NeedsAnswerProfileError, ProseVerificationError
from app.services.evidence import EvidenceBullet, EvidencePack, JDSnippet

RESUME: dict[str, Any] = {
    "contact": {"full_name": "Sam Okafor", "email": "sam@example.com"},
    "summary": "Senior backend engineer.",
    "experience": [
        {
            "company": "Nimbus Freight",
            "title": "Senior Backend Engineer",
            "start_date": "2020-05",
            "end_date": None,
            "bullets": [
                "Built Python APIs with PostgreSQL for logistics workflows.",
                "Led move from EC2 to EKS across 11 services.",
            ],
            "technologies": ["Python", "PostgreSQL", "EKS", "EC2"],
        }
    ],
    "education": [],
    "skills": [{"category": "Backend", "items": ["Python", "PostgreSQL"]}],
    "projects": [],
}

RAW_JD = (
    "Company: Corvid Logistics\n"
    "Role: Senior Backend Engineer\n"
    "The role focuses on Python backend services and PostgreSQL systems for logistics."
)


def _requirements() -> JobRequirements:
    return JobRequirements(
        hard_skills=[
            RequirementItem(term="Python", weight=1.0, evidence="Python backend services"),
            RequirementItem(term="PostgreSQL", weight=0.9, evidence="PostgreSQL systems"),
        ],
        soft_skills=[],
        domain_terms=["logistics"],
        seniority="senior",
        must_haves=["Python backend services"],
        nice_to_haves=[],
    )


def _job_target() -> JobTarget:
    # Transient; generate_short_answer only reads raw_description + requirements.
    return JobTarget(
        raw_description=RAW_JD,
        extracted_requirements=_requirements().model_dump(mode="json"),
    )


async def _fake_pack(*args: object, **kwargs: object) -> EvidencePack:
    return EvidencePack(
        bullets=[
            EvidenceBullet(
                ref="/experience/0/bullets/0",
                text="Built Python APIs with PostgreSQL for logistics workflows.",
                score=0.9,
                target="Python",
            )
        ],
        matched_skills=["Python", "PostgreSQL"],
        jd_snippets=[
            JDSnippet(
                ref="/jd/snippets/0",
                text="The role focuses on Python backend services and PostgreSQL systems.",
            )
        ],
        must_haves=["Python backend services"],
        company_or_team="Corvid Logistics",
        title="Senior Backend Engineer",
    )


def _stub_generate_once(
    output: ShortAnswerGenerationOutput,
    monkeypatch: MonkeyPatch,
) -> None:
    """Patch the pack builder and the single LLM call; leave everything else real."""

    async def fake_generate_once(
        pack: EvidencePack,
        question: str,
        kind: ShortAnswerKind,
        *,
        model: str | None,
        retry_violations: list[str] | None = None,
    ) -> tuple[ShortAnswerGenerationOutput, LLMUsage]:
        return output, LLMUsage(input_tokens=50, output_tokens=80)

    monkeypatch.setattr(sa, "build_evidence_pack", _fake_pack)
    monkeypatch.setattr(sa, "_generate_once", fake_generate_once)


def _grounded_why_company() -> str:
    return (
        "Corvid Logistics focuses on Python backend services and PostgreSQL systems, "
        "which maps directly to what I do. At Nimbus Freight I built Python APIs with "
        "PostgreSQL for logistics workflows and led the move from EC2 to EKS across 11 "
        "services. That work in logistics backends and production operations is the same "
        "ground your team is hiring for, and it is a large part of why this role and this "
        "company stand out to me right now."
    )


# --- personal-data guardrail ------------------------------------------------


@pytest.mark.parametrize(
    ("question", "expected_field"),
    [
        ("What compensation are you seeking?", "salary_min"),
        ("What is your desired salary?", "salary_min"),
        ("Are you legally authorized to work in the US?", "work_auth"),
        ("Will you now or in the future require sponsorship?", "work_auth"),
        ("What is your earliest start date?", "notice_period_days"),
        ("What is your notice period?", "notice_period_days"),
        ("Are you willing to relocate?", "relocation"),
    ],
)
def test_detect_personal_data_field(question: str, expected_field: str) -> None:
    assert sa.detect_personal_data_field(question) == expected_field


@pytest.mark.parametrize(
    "question",
    [
        "Why do you want to work here?",
        "Why are you interested in this role?",
        "Tell us about a time you improved system performance.",
        "Describe your experience with rate limiting.",  # 'rate' must not trip salary
    ],
)
def test_legitimate_questions_are_not_personal_data(question: str) -> None:
    assert sa.detect_personal_data_field(question) is None


async def test_disguised_salary_question_routes_to_answer_profile(
    monkeypatch: MonkeyPatch,
) -> None:
    # Prove the LLM is never reached: patched pack/generator would explode if called.
    async def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("generation must not run for a personal-data question")

    monkeypatch.setattr(sa, "build_evidence_pack", explode)
    monkeypatch.setattr(sa, "_generate_once", explode)

    with pytest.raises(NeedsAnswerProfileError) as excinfo:
        await sa.generate_short_answer(
            _job_target(),
            StructuredResume.model_validate(RESUME),
            "What compensation are you seeking?",
            ShortAnswerKind.custom,
        )
    assert excinfo.value.answer_profile_field == "salary_min"


# --- fabrication rejection --------------------------------------------------


async def test_invented_company_fact_is_rejected(monkeypatch: MonkeyPatch) -> None:
    output = ShortAnswerGenerationOutput(
        body_markdown=(
            "Corvid Logistics recently closed a $50M Series C round, which is exciting. "
            "At Nimbus Freight I built Python APIs with PostgreSQL for logistics workflows."
        ),
        claims_used=[
            ClaimUsed(statement="Built Python APIs", evidence_ref="/experience/0/bullets/0"),
        ],
    )
    _stub_generate_once(output, monkeypatch)

    with pytest.raises(ProseVerificationError) as excinfo:
        await sa.generate_short_answer(
            _job_target(),
            StructuredResume.model_validate(RESUME),
            "Why do you want to work here?",
            ShortAnswerKind.why_company,
        )
    assert "Series" in str(excinfo.value)


async def test_invented_personal_achievement_is_rejected(monkeypatch: MonkeyPatch) -> None:
    output = ShortAnswerGenerationOutput(
        body_markdown=(
            "At Nimbus Freight I built Python APIs with PostgreSQL for logistics workflows "
            "and personally improved API throughput by 80% across the platform."
        ),
        claims_used=[
            ClaimUsed(statement="Built Python APIs", evidence_ref="/experience/0/bullets/0"),
        ],
    )
    _stub_generate_once(output, monkeypatch)

    with pytest.raises(ProseVerificationError) as excinfo:
        await sa.generate_short_answer(
            _job_target(),
            StructuredResume.model_validate(RESUME),
            "Why are you a fit for this role?",
            ShortAnswerKind.why_role,
        )
    assert "unsupported number" in str(excinfo.value)


async def test_grounded_answer_passes(monkeypatch: MonkeyPatch) -> None:
    output = ShortAnswerGenerationOutput(
        body_markdown=_grounded_why_company(),
        claims_used=[
            ClaimUsed(statement="Built Python APIs", evidence_ref="/experience/0/bullets/0"),
            ClaimUsed(statement="Role focuses on Python", evidence_ref="/jd/snippets/0"),
        ],
    )
    _stub_generate_once(output, monkeypatch)

    result = await sa.generate_short_answer(
        _job_target(),
        StructuredResume.model_validate(RESUME),
        "Why do you want to work here?",
        ShortAnswerKind.why_company,
    )
    assert result.claim_report.passed, result.claim_report.violations
    assert 60 <= result.word_count <= 120
    assert result.question_kind == ShortAnswerKind.why_company


# --- length scaling ---------------------------------------------------------


def _words(n: int) -> str:
    return " ".join(["contribution"] * n)


@pytest.mark.parametrize(
    ("kind", "count", "should_flag"),
    [
        # why_* band is 60-120
        (ShortAnswerKind.why_company, 45, True),
        (ShortAnswerKind.why_company, 90, False),
        (ShortAnswerKind.why_role, 130, True),
        # custom band is wider: 40-150
        (ShortAnswerKind.custom, 30, True),
        (ShortAnswerKind.custom, 45, False),
        (ShortAnswerKind.custom, 140, False),
        (ShortAnswerKind.custom, 200, True),
    ],
)
def test_length_bounds_scale_by_kind(kind: ShortAnswerKind, count: int, should_flag: bool) -> None:
    violations = sa._structural_violations(_words(count), kind)
    flagged = any("word count" in v for v in violations)
    assert flagged is should_flag


def test_custom_length_guidance_mentions_estimating_from_the_question() -> None:
    guidance = sa._length_guidance(ShortAnswerKind.custom)
    assert "40" in guidance and "150" in guidance
    assert "estimate" in guidance.lower()
    # The fixed "why" prompts do not ask the model to estimate.
    assert "estimate" not in sa._length_guidance(ShortAnswerKind.why_company).lower()
