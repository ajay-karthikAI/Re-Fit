import json
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
from httpx import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobTarget, ResumeVersion
from app.schemas.jd import JobRequirements, RequirementItem
from app.schemas.llm import LLMUsage
from app.schemas.resume import StructuredResume
from app.schemas.tailor import BulletRewrite
from app.services import score as score_service
from app.services import tailor as tailor_service
from app.services.claims import verify_rewrite

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

_REWRITE_MAP = {
    "Own rate-quoting service: Go + Postgres, 8k rps peak": (
        "Built backend rate-quoting service with Go and Postgres, sustaining 8k rps peak"
    ),
    "Led move from EC2 to EKS across 11 services": (
        "Led cloud service migration from EC2 to EKS across 11 services"
    ),
    "Reduced p99 quote latency from 900ms to 210ms": (
        "Improved quote service latency, reducing p99 from 900ms to 210ms"
    ),
    "Built booking APIs in Django for 200k monthly users": (
        "Built backend booking APIs in Django for 200k monthly users"
    ),
}


class _TailorSettings:
    relevance_threshold = 0.99
    max_rewrites = 4


def _requirements() -> JobRequirements:
    return JobRequirements(
        hard_skills=[
            RequirementItem(
                term="Python",
                weight=1.0,
                evidence="Expert-level Python",
            ),
            RequirementItem(
                term="PostgreSQL",
                weight=0.95,
                evidence="Strong PostgreSQL experience",
            ),
            RequirementItem(
                term="Kafka",
                weight=0.75,
                evidence="event pipelines on Kafka",
            ),
            RequirementItem(
                term="AWS",
                weight=0.7,
                evidence="services on AWS",
            ),
        ],
        soft_skills=[],
        domain_terms=["logistics", "routing", "dispatch"],
        seniority="senior",
        must_haves=[
            "Expert-level Python",
            "Strong PostgreSQL experience",
            "Experience running services on AWS (ECS or EKS)",
        ],
        nice_to_haves=["Kafka or another event-streaming system", "Terraform"],
    )


async def _fake_embed(texts: list[str]) -> np.ndarray:
    vocabulary = [
        "python",
        "fastapi",
        "postgres",
        "postgresql",
        "kafka",
        "aws",
        "ecs",
        "eks",
        "terraform",
        "go",
        "django",
    ]
    rows = []
    for text in texts:
        lower = text.lower()
        vector = np.asarray([1.0 if token in lower else 0.0 for token in vocabulary])
        norm = np.linalg.norm(vector)
        rows.append(vector / norm if norm else vector)
    return np.stack(rows).astype(np.float32)


def _controlled_vector(index: int, similarity: float = 1.0) -> np.ndarray:
    vector = np.zeros(4, dtype=np.float32)
    vector[index] = similarity
    if similarity < 1.0:
        vector[3] = np.sqrt(1 - (similarity**2))
    return vector


def _fake_score_embed(texts: list[str]) -> np.ndarray:
    rows = []
    for text in texts:
        lower = text.lower()
        if "experience running services on aws" in lower or lower == "aws":
            rows.append(_controlled_vector(0))
        elif "postgresql" in lower:
            rows.append(_controlled_vector(1))
        elif "expert-level python" in lower:
            rows.append(_controlled_vector(2))
        elif "cloud service migration" in lower:
            rows.append(_controlled_vector(0, 0.65))
        elif "led move from ec2" in lower:
            rows.append(_controlled_vector(0, 0.55))
        elif "backend rate-quoting service" in lower:
            rows.append(_controlled_vector(1, 0.65))
        elif "own rate-quoting service" in lower:
            rows.append(_controlled_vector(1, 0.55))
        else:
            rows.append(_controlled_vector(3))
    return np.stack(rows).astype(np.float32)


async def _fake_rewrite_experience_item(
    profile: StructuredResume,
    requirements: JobRequirements,
    experience_index: int,
    candidates: list[tailor_service.BulletCandidate],
    model: str | None,
) -> tuple[list[BulletRewrite], LLMUsage]:
    rewrites = [
        BulletRewrite(
            bullet_ref=candidate.bullet_ref,
            original=candidate.original,
            rewritten=_REWRITE_MAP.get(candidate.original, candidate.original),
            requirement_targeted=candidate.requirement_targeted,
            claims_preserved=True,
        )
        for candidate in candidates
    ]
    return rewrites, LLMUsage(input_tokens=100, output_tokens=50)


def _resolve_pointer(document: Any, pointer: str) -> Any:
    current = document
    assert pointer.startswith("/")
    for raw_part in pointer.removeprefix("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


async def _make_user(client: AsyncClient, email: str) -> str:
    response = await client.post("/users", json={"email": email})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_tailor_api_persists_version_and_returns_verified_diff(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(tailor_service, "get_settings", lambda: _TailorSettings())
    monkeypatch.setattr(tailor_service, "_embed", _fake_embed)
    monkeypatch.setattr(score_service, "_embed_texts", _fake_score_embed)
    monkeypatch.setattr(
        tailor_service,
        "_rewrite_experience_item",
        _fake_rewrite_experience_item,
    )

    user_id = await _make_user(client, "tailor-integration@example.com")
    response = await client.put(f"/users/{user_id}/profile", json=CORPUS_RESUME)
    assert response.status_code == 200, response.text
    profile_id = response.json()["id"]

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
    requirements = _requirements()
    job_target.extracted_requirements = requirements.model_dump(mode="json")
    await session.commit()

    response = await client.post(
        f"/profiles/{profile_id}/tailor",
        json={"job_target_id": job_target_id},
    )
    assert response.status_code == 200, response.text
    result = response.json()

    assert result["version_id"]
    assert result["stats"]["rewrites_accepted"] >= 1
    assert result["stats"]["rewrites_discarded"] == 0
    assert result["score_before"] is not None
    assert result["score_after"] is not None
    assert result["score_after"]["headline_score"] >= result["score_before"]["headline_score"]
    assert len(result["score_after"]["keyword_coverage"]["missing_terms"]) < len(
        result["score_before"]["keyword_coverage"]["missing_terms"]
    )
    version = await session.get(ResumeVersion, UUID(result["version_id"]))
    assert version is not None
    assert version.score_cache is not None
    assert version.score_cache["headline_score"] == result["score_after"]["headline_score"]

    score_response = await client.get(
        f"/versions/{result['version_id']}/score",
        params={"job_target_id": job_target_id},
    )
    assert score_response.status_code == 200, score_response.text
    assert score_response.json() == result["score_after"]

    tailored_resume = result["resume"]
    source_resume = StructuredResume.model_validate(CORPUS_RESUME)
    bullet_diffs = [entry for entry in result["diff"] if entry["bullet_ref"] != "/skills"]
    assert bullet_diffs

    for entry in result["diff"]:
        assert _resolve_pointer(tailored_resume, entry["bullet_ref"]) == entry["after"]

    for entry in bullet_diffs:
        experience_index = int(entry["bullet_ref"].split("/")[2])
        verification = verify_rewrite(
            original=entry["before"],
            rewritten=entry["after"],
            profile=source_resume,
            requirements=requirements,
            parent_experience=source_resume.experience[experience_index],
        )
        assert verification.passed, verification.reasons

    first = bullet_diffs[0]
    print(
        "\nIntegration before/after diff:\n"
        f"{first['bullet_ref']}\n"
        f"- {first['before']}\n"
        f"+ {first['after']}"
    )
    score_json = {
        "before": {
            "headline_score": result["score_before"]["headline_score"],
            "keyword_coverage": {
                "score": result["score_before"]["keyword_coverage"]["score"],
                "missing_terms": result["score_before"]["keyword_coverage"]["missing_terms"],
            },
        },
        "after": {
            "headline_score": result["score_after"]["headline_score"],
            "keyword_coverage": {
                "score": result["score_after"]["keyword_coverage"]["score"],
                "missing_terms": result["score_after"]["keyword_coverage"]["missing_terms"],
            },
        },
    }
    print("\nIntegration before/after score JSON:\n" + json.dumps(score_json, indent=2))
