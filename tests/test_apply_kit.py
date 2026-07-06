"""ApplyKit assembly: full compose against a corpus job target, with a complete
and an empty answer profile, targeted single-field regeneration, and checklist
ordering pinned to the declared ATS field order.

Only the model calls are stubbed (tailor, cover letter, short-answer LLM). The
composition, field plan, verify_prose gate, rendering, checklist ordering, and
gap detection all run for real.
"""

import collections
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
from httpx import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.ats_fields import FIELD_TAXONOMY
from app.models import JobTarget, ShortAnswer
from app.models.short_answer import ShortAnswerKind, hash_question
from app.schemas.cover_letter import CoverLetterResult, ProseClaimReport
from app.schemas.jd import JobRequirements, RequirementItem
from app.schemas.llm import LLMUsage
from app.schemas.short_answer import ShortAnswerGenerationOutput
from app.schemas.cover_letter import ClaimUsed
from app.schemas.tailor import TailorDiffEntry, TailorResult, TailorStats
from app.services import kit as kit_service
from app.services import score as score_service
from app.services import short_answers as sa
from app.services.evidence import EvidenceBullet, EvidencePack, JDSnippet

CORPUS_JD = Path(__file__).parent / "corpus" / "jds" / "synthetic_backend_jd.txt"
GREENHOUSE_URL = "https://boards.greenhouse.io/corvid/jobs/4567890"

CORPUS_RESUME: dict[str, Any] = {
    "contact": {
        "full_name": "Sam Okafor",
        "email": "sam.okafor@example.com",
        "phone": "(555) 019-4452",
        "location": "Chicago, IL",
        "linkedin_url": "https://www.linkedin.com/in/sam",
    },
    "summary": "Senior backend engineer.",
    "experience": [
        {
            "company": "Nimbus Freight",
            "title": "Senior Backend Engineer",
            "start_date": "2020-05",
            "end_date": None,
            "bullets": [
                "Own rate-quoting service: Go + Postgres, 8k rps peak",
                "Led move from EC2 to EKS across 11 services",
                "Reduced p99 quote latency from 900ms to 210ms",
            ],
            "technologies": ["Go", "Postgres", "EKS", "EC2"],
        }
    ],
    "education": [],
    "skills": [{"category": "Backend", "items": ["Go", "Python", "Postgres"]}],
    "projects": [],
}

COMPLETE_ANSWER_PROFILE: dict[str, Any] = {
    "work_auth": "citizen",
    "sponsorship_needed": False,
    "salary_min": 150000,
    "salary_max": 185000,
    "salary_currency": "USD",
    "salary_type": "annual",
    "relocation": "yes",
    "notice_period_days": 14,
    "pronouns": "they/them",
    "referral_source_default": "Company careers page",
    "eeo_prefs": None,
}

WHY_COMPANY_BODY = (
    "Corvid Logistics builds routing and dispatch software for regional freight "
    "carriers, and that logistics focus fits my background. At Nimbus Freight I built "
    "a backend rate-quoting service with Go and Postgres, led the move from EC2 to EKS "
    "across 11 services, and reduced p99 quote latency from 900ms to 210ms. That routing "
    "and dispatch experience is a large part of why this company stands out to me."
)
CUSTOM_BODY = (
    "At Nimbus Freight I built a backend rate-quoting service with Go and Postgres and "
    "led the move from EC2 to EKS across 11 services. I approach hard problems by reducing "
    "them to measurable goals, the way I cut p99 quote latency from 900ms to 210ms."
)
CUSTOM_QUESTION = "Describe a hard technical problem you solved."


def _requirements() -> JobRequirements:
    return JobRequirements(
        hard_skills=[
            RequirementItem(term="Python", weight=1.0, evidence="Expert-level Python"),
            RequirementItem(term="PostgreSQL", weight=0.95, evidence="Strong PostgreSQL"),
            RequirementItem(term="AWS", weight=0.7, evidence="services on AWS"),
        ],
        soft_skills=[],
        domain_terms=["logistics", "routing", "dispatch"],
        seniority="senior",
        must_haves=["Experience running services on AWS (ECS or EKS)"],
        nice_to_haves=["Kafka"],
    )


def _zero_embed(texts: list[str]) -> np.ndarray:
    return np.zeros((len(texts), 4), dtype=np.float32)


async def _fake_pack(*args: object, **kwargs: object) -> EvidencePack:
    return EvidencePack(
        bullets=[
            EvidenceBullet(
                ref="/experience/0/bullets/0",
                text="Built a backend rate-quoting service with Go and Postgres.",
                score=0.9,
                target="PostgreSQL",
            )
        ],
        matched_skills=["Go", "Postgres"],
        jd_snippets=[
            JDSnippet(
                ref="/jd/snippets/0",
                text="Corvid Logistics builds routing and dispatch software for freight carriers.",
            )
        ],
        must_haves=["Experience running services on AWS (ECS or EKS)"],
        company_or_team="Corvid Logistics",
        title="Senior Backend Engineer",
    )


def _install_stubs(monkeypatch: MonkeyPatch) -> dict[str, Any]:
    """Stub only the model calls; return counters so tests can prove what ran."""
    calls: dict[str, Any] = {
        "tailor": 0,
        "cover": 0,
        "short_answer": collections.Counter(),
    }

    def fake_put_object(key: str, body: bytes, content_type: str) -> None:
        return None

    def fake_presigned_get_url(key: str, expires_in: int = 900) -> str:
        return f"https://storage.example.test/{key}"

    async def fake_tailor(
        profile: Any, requirements: JobRequirements, **kwargs: Any
    ) -> TailorResult:
        calls["tailor"] += 1
        tailored = profile.model_copy(deep=True)
        before = tailored.experience[0].bullets[0]
        after = "Built a backend rate-quoting service with Go and Postgres, sustaining 8k rps peak"
        tailored.experience[0].bullets[0] = after
        return TailorResult(
            resume=tailored,
            diff=[
                TailorDiffEntry(
                    bullet_ref="/experience/0/bullets/0",
                    before=before,
                    after=after,
                    requirement_targeted="PostgreSQL",
                )
            ],
            stats=TailorStats(
                bullets_scored=3,
                rewrite_candidates=1,
                experience_items_rewritten=1,
                rewrites_requested=1,
                rewrites_returned=1,
                rewrites_accepted=1,
                rewrites_discarded=0,
                skills_reordered=False,
                relevance_threshold=0.45,
                max_rewrites=8,
                usage=LLMUsage(input_tokens=100, output_tokens=50),
            ),
        )

    async def fake_cover_letter(*args: Any, **kwargs: Any) -> CoverLetterResult:
        calls["cover"] += 1
        return CoverLetterResult(
            body_markdown=(
                "Dear Corvid Logistics team,\n\n"
                "At Nimbus Freight I built backend services with Go and Postgres."
            ),
            word_count=13,
            claim_report=ProseClaimReport(passed=True),
            usage=LLMUsage(input_tokens=70, output_tokens=30),
        )

    async def fake_generate_once(
        pack: EvidencePack,
        question: str,
        kind: ShortAnswerKind,
        *,
        model: str | None,
        retry_violations: list[str] | None = None,
    ) -> tuple[ShortAnswerGenerationOutput, LLMUsage]:
        calls["short_answer"][question] += 1
        body = WHY_COMPANY_BODY if kind is ShortAnswerKind.why_company else CUSTOM_BODY
        output = ShortAnswerGenerationOutput(
            body_markdown=body,
            claims_used=[
                ClaimUsed(
                    statement="Built backend service", evidence_ref="/experience/0/bullets/0"
                ),
                ClaimUsed(statement="Corvid builds routing", evidence_ref="/jd/snippets/0"),
            ],
        )
        return output, LLMUsage(input_tokens=40, output_tokens=70)

    monkeypatch.setattr(kit_service.storage, "put_object", fake_put_object)
    monkeypatch.setattr(kit_service.storage, "presigned_get_url", fake_presigned_get_url)
    monkeypatch.setattr(kit_service, "tailor", fake_tailor)
    monkeypatch.setattr(kit_service, "generate_cover_letter", fake_cover_letter)
    monkeypatch.setattr(score_service, "_embed_texts", _zero_embed)
    monkeypatch.setattr(sa, "build_evidence_pack", _fake_pack)
    monkeypatch.setattr(sa, "_generate_once", fake_generate_once)
    return calls


async def _setup_job_target(
    client: AsyncClient,
    session: AsyncSession,
    *,
    email: str,
    answer_profile: dict[str, Any] | None,
) -> str:
    response = await client.post("/users", json={"email": email})
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]

    response = await client.put(f"/users/{user_id}/profile", json=CORPUS_RESUME)
    assert response.status_code == 200, response.text

    if answer_profile is not None:
        response = await client.put(f"/users/{user_id}/answer-profile", json=answer_profile)
        assert response.status_code == 200, response.text

    response = await client.post(
        f"/users/{user_id}/job-targets",
        json={
            "raw_description": CORPUS_JD.read_text(),
            "company": "Corvid Logistics",
            "title": "Senior Backend Engineer",
            "source_url": GREENHOUSE_URL,
        },
    )
    assert response.status_code == 201, response.text
    job_target_id = response.json()["id"]
    assert response.json()["source_ats"] == "greenhouse"

    job_target = await session.get(JobTarget, UUID(job_target_id))
    assert job_target is not None
    job_target.extracted_requirements = _requirements().model_dump(mode="json")
    await session.commit()
    return job_target_id


async def test_apply_kit_complete_answer_profile_all_ready(
    client: AsyncClient, session: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    _install_stubs(monkeypatch)
    job_target_id = await _setup_job_target(
        client, session, email="apply-complete@example.com", answer_profile=COMPLETE_ANSWER_PROFILE
    )

    response = await client.get(f"/job-targets/{job_target_id}/apply-kit")
    assert response.status_code == 200, response.text
    kit = response.json()

    assert kit["source_ats"] == "greenhouse"
    assert kit["source_url"] == GREENHOUSE_URL
    assert kit["answer_profile_gaps"] == []

    by_key = {item["field_spec"]["key"]: item for item in kit["field_plan"]}
    # Nothing left unresolved: no needs_generation / needs_user_input / error anywhere.
    assert all(item["status"] in ("ready", "manual_only") for item in kit["field_plan"]), [
        (i["field_spec"]["key"], i["status"]) for i in kit["field_plan"]
    ]
    assert by_key["why_company"]["status"] == "ready"
    assert "Corvid Logistics" in by_key["why_company"]["resolved_value"]
    assert by_key["desired_salary"]["resolved_value"] == "150,000-185,000 USD (annual)"
    assert by_key["eeo"]["status"] == "manual_only"

    docs = {doc["key"]: doc for doc in kit["documents"]}
    assert docs["resume_pdf"]["ready"] is True
    assert docs["resume_pdf"]["download_url"].startswith("https://storage.example.test/")
    assert docs["cover_letter_pdf"]["ready"] is True


async def test_apply_kit_checklist_order_matches_taxonomy(
    client: AsyncClient, session: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    _install_stubs(monkeypatch)
    job_target_id = await _setup_job_target(
        client, session, email="apply-checklist@example.com", answer_profile=COMPLETE_ANSWER_PROFILE
    )

    response = await client.get(f"/job-targets/{job_target_id}/apply-kit")
    assert response.status_code == 200, response.text
    checklist = response.json()["checklist"]

    field_steps = [step for step in checklist if step["field_key"] is not None]
    assert [step["field_key"] for step in field_steps] == [
        spec.key for spec in FIELD_TAXONOMY["greenhouse"]
    ]
    # Orders are contiguous and the terminal step is submit.
    assert [step["order"] for step in checklist] == list(range(1, len(checklist) + 1))
    assert checklist[-1]["field_key"] is None
    assert checklist[-1]["action"] == "submit"


async def test_apply_kit_empty_answer_profile_populates_gaps(
    client: AsyncClient, session: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    _install_stubs(monkeypatch)
    job_target_id = await _setup_job_target(
        client, session, email="apply-empty@example.com", answer_profile=None
    )

    response = await client.get(f"/job-targets/{job_target_id}/apply-kit")
    assert response.status_code == 200, response.text
    kit = response.json()

    gap_fields = {gap["field"] for gap in kit["answer_profile_gaps"]}
    assert gap_fields == {
        "work_auth",
        "sponsorship_needed",
        "relocation",
        "salary_min",
        "referral_source_default",
    }
    for gap in kit["answer_profile_gaps"]:
        assert gap["link_target"] == f"/answer-profile?field={gap['field']}"

    by_key = {item["field_spec"]["key"]: item for item in kit["field_plan"]}
    # Answer-profile fields are flagged, but generation that needs no answer
    # profile still succeeds.
    assert by_key["work_authorization"]["status"] == "needs_user_input"
    assert by_key["why_company"]["status"] == "ready"
    assert "Corvid Logistics" in by_key["why_company"]["resolved_value"]
    # Contact + document fields resolve regardless of the answer profile.
    assert by_key["name"]["status"] == "ready"
    assert by_key["resume_upload"]["status"] == "ready"


async def test_regenerate_one_field_leaves_siblings_untouched(
    client: AsyncClient, session: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    calls = _install_stubs(monkeypatch)
    job_target_id = await _setup_job_target(
        client, session, email="apply-regen@example.com", answer_profile=COMPLETE_ANSWER_PROFILE
    )

    # First assemble generates the why_company answer.
    response = await client.get(f"/job-targets/{job_target_id}/apply-kit")
    assert response.status_code == 200, response.text
    assert calls["short_answer"]["Why do you want to work here?"] == 1

    # Seed a sibling short answer (a custom question) now that a version exists.
    response = await client.post(
        f"/job-targets/{job_target_id}/short-answers",
        json={"question": CUSTOM_QUESTION, "question_kind": "custom"},
    )
    assert response.status_code == 200, response.text
    assert calls["short_answer"][CUSTOM_QUESTION] == 1

    sibling_before = (
        await session.execute(
            select(ShortAnswer).where(
                ShortAnswer.job_target_id == UUID(job_target_id),
                ShortAnswer.question_hash == hash_question(CUSTOM_QUESTION),
            )
        )
    ).scalar_one()
    sibling_created_at = sibling_before.created_at
    sibling_answer = sibling_before.answer_markdown

    # Regenerate exactly one field.
    response = await client.post(
        f"/job-targets/{job_target_id}/apply-kit/regenerate",
        json={"field_key": "why_company"},
    )
    assert response.status_code == 200, response.text
    by_key = {item["field_spec"]["key"]: item for item in response.json()["field_plan"]}
    assert by_key["why_company"]["status"] == "ready"

    # The forced field re-ran once more; the sibling was never touched.
    assert calls["short_answer"]["Why do you want to work here?"] == 2
    assert calls["short_answer"][CUSTOM_QUESTION] == 1

    session.expire_all()
    sibling_after = (
        await session.execute(
            select(ShortAnswer).where(
                ShortAnswer.job_target_id == UUID(job_target_id),
                ShortAnswer.question_hash == hash_question(CUSTOM_QUESTION),
            )
        )
    ).scalar_one()
    assert sibling_after.created_at == sibling_created_at
    assert sibling_after.answer_markdown == sibling_answer


async def test_apply_kit_does_not_create_application_but_track_does(
    client: AsyncClient, session: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    _install_stubs(monkeypatch)
    job_target_id = await _setup_job_target(
        client, session, email="apply-track@example.com", answer_profile=COMPLETE_ANSWER_PROFILE
    )
    user_id = (await session.get(JobTarget, UUID(job_target_id))).user_id  # type: ignore[union-attr]

    # Viewing the kit must not create an Application.
    response = await client.get(f"/job-targets/{job_target_id}/apply-kit")
    assert response.status_code == 200, response.text
    apps = await client.get(f"/users/{user_id}/applications")
    assert apps.json() == []

    # Track creates one, and is idempotent.
    first = await client.post(f"/job-targets/{job_target_id}/track", json={})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "applied"
    second = await client.post(f"/job-targets/{job_target_id}/track", json={})
    assert second.json()["id"] == first.json()["id"]

    apps = await client.get(f"/users/{user_id}/applications")
    assert len(apps.json()) == 1
