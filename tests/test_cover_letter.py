from pathlib import Path
from typing import Any

import numpy as np
from pytest import MonkeyPatch

from app.config import get_settings
from app.schemas.cover_letter import CoverLetterOutput, ClaimUsed
from app.schemas.jd import JobRequirements, RequirementItem
from app.schemas.llm import LLMUsage
from app.schemas.resume import StructuredResume
from app.services import cover_letter as cover_letter_service
from app.services.render import render_cover_letter_docx_result, render_cover_letter_pdf_result

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


def _grounded_letter() -> str:
    return (
        "Dear Corvid Logistics team,\n\n"
        "Corvid Logistics builds routing and dispatch software for regional freight "
        "carriers. At Nimbus Freight, I owned a rate-quoting service in Go and "
        "Postgres with 8k rps peak, led the move from EC2 to EKS across 11 services, "
        "and reduced p99 quote latency from 900ms to 210ms. That evidence gives me "
        "a practical base for backend services, heavy write load, and AWS operations.\n\n"
        "In the tailored resume evidence, the strongest overlap is production ownership. "
        "The rate-quoting service shows work close to routing, dispatch, and logistics "
        "software, while the EC2 to EKS migration shows service operation across a "
        "real platform boundary. The latency work shows attention to query and service "
        "performance, and the profile also includes Python, Postgres, Kafka, Terraform, "
        "Go, Django, and gRPC as named skills or technologies.\n\n"
        "For Corvid Logistics, I would connect those experiences to the Python/FastAPI "
        "backend, PostgreSQL schema work, Kafka event pipelines, and AWS ECS or EKS "
        "operations described in the role. At Parkside Labs, I also built booking APIs "
        "in Django for 200k monthly users, which supports the API ownership expected "
        "for production backend systems.\n\n"
        "The evidence I would bring is straightforward: operating services with clear "
        "latency goals, moving infrastructure across EC2 and EKS, and keeping backend "
        "systems useful for product workflows. The profile also shows backend API "
        "work in Django for 200k monthly users and practical use of Go, Postgres, "
        "Kafka, Terraform, and Python. That is the same kind of ownership Corvid "
        "Logistics names for engineers who communicate proactively and leave "
        "codebases better than they found them."
    )


async def test_generate_cover_letter_corpus_pair(
    monkeypatch: MonkeyPatch,
) -> None:
    async def fake_generate_once(
        pack: cover_letter_service.EvidencePack,
        tone: str,
        *,
        model: str | None,
        retry_violations: list[str] | None = None,
    ) -> tuple[CoverLetterOutput, LLMUsage]:
        return (
            CoverLetterOutput(
                body_markdown=_grounded_letter(),
                claims_used=[
                    ClaimUsed(
                        statement="Owned a Go and Postgres rate-quoting service",
                        evidence_ref=pack.bullets[0].ref,
                    ),
                    ClaimUsed(
                        statement="Corvid Logistics builds routing and dispatch software",
                        evidence_ref=pack.jd_snippets[0].ref,
                    ),
                ],
            ),
            LLMUsage(input_tokens=100, output_tokens=200),
        )

    monkeypatch.setattr(cover_letter_service, "_embed", _fake_embed)
    monkeypatch.setattr(cover_letter_service, "_generate_once", fake_generate_once)

    profile = StructuredResume.model_validate(CORPUS_RESUME)
    result = await cover_letter_service.generate_cover_letter(
        profile,
        _requirements(),
        CORPUS_JD.read_text(),
        profile,
        tone="standard",
    )

    assert 250 <= result.word_count <= 350
    assert result.claim_report.passed, result.claim_report.violations
    assert not result.claim_report.violations
    lower = result.body_markdown.lower()
    for phrase in get_settings().cover_letter_banned_phrases:
        assert phrase.lower() not in lower


def test_render_cover_letter_pdf_and_docx() -> None:
    profile = StructuredResume.model_validate(CORPUS_RESUME)

    pdf = render_cover_letter_pdf_result(profile, _grounded_letter())
    docx = render_cover_letter_docx_result(profile, _grounded_letter())

    assert pdf.page_count == 1
    assert pdf.content.startswith(b"%PDF")
    assert docx.content.startswith(b"PK")
