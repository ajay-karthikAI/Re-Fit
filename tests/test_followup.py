from datetime import date, datetime, timezone
import uuid

from pytest import MonkeyPatch

from app.models import Application, ApplicationStatus, FollowupKind
from app.schemas.cover_letter import ClaimUsed
from app.schemas.followup import FollowupOutput
from app.schemas.jd import JobRequirements, RequirementItem
from app.schemas.llm import LLMUsage
from app.schemas.resume import StructuredResume
from app.services import followup as followup_service
from app.services.cover_letter import EvidenceBullet, EvidencePack, JDSnippet


def _profile() -> StructuredResume:
    return StructuredResume(
        contact={"full_name": "Sam Okafor", "email": "sam@example.com"},
        summary="Backend engineer.",
        experience=[
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
        education=[],
        skills=[{"category": "Backend", "items": ["Python", "PostgreSQL"]}],
        projects=[],
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


def _application() -> Application:
    return Application(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        job_target_id=uuid.uuid4(),
        resume_version_id=uuid.uuid4(),
        status=ApplicationStatus.applied,
        applied_at=datetime(2026, 7, 6, tzinfo=timezone.utc),
    )


def _context() -> followup_service.FollowupGenerationContext:
    profile = _profile()
    return followup_service.FollowupGenerationContext(
        application=_application(),
        profile=profile,
        requirements=_requirements(),
        raw_jd=(
            "Company: Corvid Logistics\n"
            "Role: Senior Backend Engineer\n"
            "The role focuses on Python backend services and PostgreSQL systems."
        ),
        resume_version=profile,
        company="Corvid Logistics",
        title="Senior Backend Engineer",
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


def test_add_business_days_skips_weekends() -> None:
    assert followup_service.add_business_days(date(2026, 7, 6), 5) == date(2026, 7, 13)
    assert followup_service.add_business_days(date(2026, 7, 10), 1) == date(2026, 7, 13)
    assert followup_service.add_business_days(date(2026, 7, 11), 1) == date(2026, 7, 13)


async def test_post_interview_followup_contains_placeholder_and_passes(
    monkeypatch: MonkeyPatch,
) -> None:
    async def fake_generate_once(
        pack: EvidencePack,
        context: followup_service.FollowupGenerationContext,
        kind: FollowupKind,
        *,
        model: str | None,
        retry_violations: list[str] | None = None,
    ) -> tuple[FollowupOutput, LLMUsage]:
        return (
            FollowupOutput(
                subject="Thank you - Senior Backend Engineer",
                body_markdown=(
                    "Thank you for speaking with me about the Senior Backend Engineer role "
                    "at Corvid Logistics. [PERSONAL DETAIL FROM YOUR CONVERSATION] The role "
                    "focuses on Python backend services and PostgreSQL systems, and that maps "
                    "to my experience building Python APIs with PostgreSQL for logistics "
                    "workflows. I appreciate the time and remain interested in contributing "
                    "to the backend work described in the role. That combination is the same "
                    "practical backend work described in the role, so I remain interested in "
                    "contributing where it fits."
                ),
                claims_used=[
                    ClaimUsed(
                        statement="Python APIs with PostgreSQL",
                        evidence_ref="/experience/0/bullets/0",
                    ),
                    ClaimUsed(
                        statement="Python backend services and PostgreSQL systems",
                        evidence_ref="/jd/snippets/0",
                    ),
                ],
            ),
            LLMUsage(input_tokens=11, output_tokens=7),
        )

    monkeypatch.setattr(followup_service, "_build_evidence_pack", _fake_pack)
    monkeypatch.setattr(followup_service, "_generate_once", fake_generate_once)

    result = await followup_service.generate_followup(_context(), FollowupKind.post_interview)

    assert followup_service.INTERVIEW_PLACEHOLDER in result.body_markdown
    assert result.claim_report.passed, result.claim_report.violations
    assert not result.claim_report.violations
    assert result.send_after == date(2026, 7, 7)
