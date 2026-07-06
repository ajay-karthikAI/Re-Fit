from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
from httpx import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobTarget
from app.schemas.cover_letter import CoverLetterResult, ProseClaimReport
from app.schemas.jd import JobRequirements, RequirementItem
from app.schemas.llm import LLMUsage
from app.schemas.tailor import TailorDiffEntry, TailorResult, TailorStats
from app.services import kit as kit_service
from app.services import score as score_service

CORPUS_JD = Path(__file__).parent / "corpus" / "jds" / "synthetic_backend_jd.txt"

CORPUS_RESUME: dict[str, Any] = {
    "contact": {
        "full_name": "Sam Okafor",
        "email": "sam.okafor@example.com",
        "phone": "(555) 019-4452",
        "location": "Chicago, IL",
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
        },
        {
            "company": "Parkside Labs",
            "title": "Backend Engineer",
            "start_date": "2017-09",
            "end_date": "2020-04",
            "bullets": ["Built booking APIs in Django for 200k monthly users"],
            "technologies": ["Django"],
        },
    ],
    "education": [
        {
            "institution": "University of Illinois Chicago",
            "degree": "BEng",
            "field": "Software Engineering",
            "graduation_date": "2017-05",
            "details": [],
        }
    ],
    "skills": [
        {"category": "Backend", "items": ["Go", "Python", "Postgres", "gRPC"]},
        {"category": "Platform", "items": ["Kubernetes", "Kafka", "Terraform"]},
    ],
    "projects": [],
}


def _requirements() -> JobRequirements:
    return JobRequirements(
        hard_skills=[
            RequirementItem(term="Python", weight=1.0, evidence="Expert-level Python"),
            RequirementItem(term="PostgreSQL", weight=0.95, evidence="Strong PostgreSQL"),
            RequirementItem(term="AWS", weight=0.7, evidence="services on AWS"),
        ],
        soft_skills=[],
        domain_terms=["logistics"],
        seniority="senior",
        must_haves=["Experience running services on AWS (ECS or EKS)"],
        nice_to_haves=["Kafka"],
    )


def _zero_embed(texts: list[str]) -> np.ndarray:
    return np.zeros((len(texts), 4), dtype=np.float32)


async def _make_user(client: AsyncClient, email: str) -> str:
    response = await client.post("/users", json={"email": email})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_kit_endpoint_is_idempotent(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: MonkeyPatch,
) -> None:
    stored: dict[str, bytes] = {}
    calls = {"tailor": 0, "cover": 0, "put": 0}

    def fake_put_object(key: str, body: bytes, content_type: str) -> None:
        calls["put"] += 1
        stored[key] = body

    def fake_presigned_get_url(key: str, expires_in: int = 900) -> str:
        return f"https://storage.example.test/{key}?expires={expires_in}"

    async def fake_tailor(
        profile: Any, requirements: JobRequirements, **kwargs: Any
    ) -> TailorResult:
        calls["tailor"] += 1
        tailored = profile.model_copy(deep=True)
        before = tailored.experience[0].bullets[0]
        after = "Built backend rate-quoting service with Go and Postgres, sustaining 8k rps peak"
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
                bullets_scored=4,
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
                "My experience building backend services with Go, Postgres, EC2, and EKS "
                "maps to the role's backend systems focus."
            ),
            word_count=24,
            claim_report=ProseClaimReport(passed=True),
            usage=LLMUsage(input_tokens=70, output_tokens=30),
        )

    monkeypatch.setattr(kit_service.storage, "put_object", fake_put_object)
    monkeypatch.setattr(kit_service.storage, "presigned_get_url", fake_presigned_get_url)
    monkeypatch.setattr(kit_service, "tailor", fake_tailor)
    monkeypatch.setattr(kit_service, "generate_cover_letter", fake_cover_letter)
    monkeypatch.setattr(score_service, "_embed_texts", _zero_embed)

    user_id = await _make_user(client, "kit@example.com")
    response = await client.put(f"/users/{user_id}/profile", json=CORPUS_RESUME)
    assert response.status_code == 200, response.text

    response = await client.post(
        f"/users/{user_id}/job-targets",
        json={
            "raw_description": CORPUS_JD.read_text(),
            "company": "Corvid Logistics",
            "title": "Senior Backend Engineer",
        },
    )
    assert response.status_code == 201, response.text
    job_target_id = response.json()["id"]

    job_target = await session.get(JobTarget, UUID(job_target_id))
    assert job_target is not None
    job_target.extracted_requirements = _requirements().model_dump(mode="json")
    await session.commit()

    first = await client.post(f"/job-targets/{job_target_id}/kit", json={})
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert first_payload["usage"] == {"input_tokens": 170, "output_tokens": 80}
    assert first_payload["diff_summary"]["bullet_rewrites"] == 1
    assert calls == {"tailor": 1, "cover": 1, "put": 2}

    second = await client.post(f"/job-targets/{job_target_id}/kit", json={})
    assert second.status_code == 200, second.text
    second_payload = second.json()
    assert second_payload["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert second_payload["resume_version_id"] == first_payload["resume_version_id"]
    assert second_payload["cover_letter_id"] == first_payload["cover_letter_id"]
    assert calls == {"tailor": 1, "cover": 1, "put": 2}

    get_response = await client.get(f"/job-targets/{job_target_id}/kit")
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["usage"] == {"input_tokens": 0, "output_tokens": 0}
