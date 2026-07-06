"""Dashboard tracker endpoints: kit availability on the applications list and
the per-application kit detail view."""

import uuid
from typing import Any

from httpx import AsyncClient
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CoverLetter, CoverLetterTone, Document, DocumentKind, Followup
from app.models import FollowupKind, ResumeVersion
from app.schemas.score import (
    ATSScore,
    FormatHealthBreakdown,
    KeywordCoverageBreakdown,
    LengthDensityBreakdown,
    SectionIntegrityBreakdown,
)
from app.services import storage
from app.services.score_cache import build_score_cache

RESUME: dict[str, Any] = {
    "contact": {"full_name": "Test Person", "email": "tp@example.com"},
    "summary": "Engineer.",
    "experience": [
        {
            "company": "Acme",
            "title": "Engineer",
            "start_date": "2020-01",
            "end_date": None,
            "bullets": ["Built the thing."],
            "technologies": ["Python"],
        }
    ],
    "education": [],
    "skills": [{"category": "Languages", "items": ["Python"]}],
    "projects": [],
}


def _ats_score(headline: float, missing_terms: list[str] | None = None) -> ATSScore:
    return ATSScore(
        headline_score=headline,
        components=[],
        keyword_coverage=KeywordCoverageBreakdown(
            score=headline / 100, missing_terms=missing_terms or []
        ),
        section_integrity=SectionIntegrityBreakdown(score=1.0),
        format_health=FormatHealthBreakdown(),
        length_and_density=LengthDensityBreakdown(
            score=1.0,
            estimated_pages=1,
            word_count=300,
            average_bullet_words=12.0,
            first_person_pronouns=0,
        ),
    )


async def _make_application(client: AsyncClient, email: str) -> dict[str, str]:
    """user -> profile -> job target -> version -> application, all through the API."""
    response = await client.post("/users", json={"email": email})
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]

    response = await client.put(f"/users/{user_id}/profile", json=RESUME)
    assert response.status_code == 200, response.text
    profile_id = response.json()["id"]

    response = await client.post(
        f"/users/{user_id}/job-targets",
        json={"raw_description": "Great job.", "company": "Initech", "title": "Staff Engineer"},
    )
    assert response.status_code == 201, response.text
    job_target_id = response.json()["id"]

    response = await client.post(
        f"/profiles/{profile_id}/versions",
        json={"job_target_id": job_target_id, "label": "Initech v1"},
    )
    assert response.status_code == 201, response.text
    version_id = response.json()["id"]

    response = await client.post(
        f"/users/{user_id}/applications",
        json={
            "job_target_id": job_target_id,
            "resume_version_id": version_id,
            "status": "applied",
        },
    )
    assert response.status_code == 201, response.text
    return {
        "user_id": user_id,
        "profile_id": profile_id,
        "job_target_id": job_target_id,
        "version_id": version_id,
        "application_id": response.json()["id"],
    }


async def _attach_kit_pieces(session: AsyncSession, ids: dict[str, str]) -> None:
    version_id = uuid.UUID(ids["version_id"])
    version = await session.get(ResumeVersion, version_id)
    assert version is not None
    score_after = _ats_score(81.0, missing_terms=["Kafka"])
    version.diff = {
        "score_before": _ats_score(62.0, missing_terms=["Kafka", "Go"]).model_dump(mode="json"),
        "score_after": score_after.model_dump(mode="json"),
    }
    version.score_cache = build_score_cache(uuid.UUID(ids["job_target_id"]), score_after)

    session.add(
        Document(
            resume_version_id=version_id,
            kind=DocumentKind.resume_pdf,
            s3_key=f"documents/{ids['user_id']}/{version_id}/resume_pdf.pdf",
        )
    )
    cover = CoverLetter(
        job_target_id=uuid.UUID(ids["job_target_id"]),
        resume_version_id=version_id,
        body_markdown="I built the thing at Acme.",
        tone=CoverLetterTone.standard,
        word_count=6,
        claim_report={
            "passed": True,
            "violations": [],
            "proper_nouns_checked": ["Acme", "Initech"],
            "numbers_checked": ["2020"],
            "company_fact_sentences_checked": [],
        },
    )
    session.add(cover)
    for kind in (FollowupKind.post_apply, FollowupKind.checkin):
        session.add(
            Followup(
                application_id=uuid.UUID(ids["application_id"]),
                kind=kind,
                subject=f"{kind.value} subject",
                body_markdown="Following up.",
                send_after=None,
            )
        )
    await session.commit()


async def test_list_applications_reports_kit_availability(
    client: AsyncClient, session: AsyncSession
) -> None:
    ids = await _make_application(client, "dash-list@example.com")

    response = await client.get(f"/users/{ids['user_id']}/applications")
    assert response.status_code == 200
    row = response.json()[0]
    assert row["resume_pdf_ready"] is False
    assert row["has_cover_letter"] is False
    assert row["followup_count"] == 0
    assert row["ats_score"] is None
    assert row["last_activity_at"] == row["updated_at"]

    await _attach_kit_pieces(session, ids)

    response = await client.get(f"/users/{ids['user_id']}/applications")
    assert response.status_code == 200
    row = response.json()[0]
    assert row["resume_pdf_ready"] is True
    assert row["has_cover_letter"] is True
    assert row["followup_count"] == 2
    assert row["ats_score"] == 81.0
    # Followups were created after the application row, so they are the latest activity.
    assert row["last_activity_at"] >= row["updated_at"]


async def test_application_kit_detail(
    client: AsyncClient, session: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(
        storage,
        "presigned_get_url",
        lambda key, expires_in=900: f"https://storage.example.test/{key}",
    )
    ids = await _make_application(client, "dash-kit@example.com")
    await _attach_kit_pieces(session, ids)

    response = await client.get(f"/applications/{ids['application_id']}/kit")
    assert response.status_code == 200, response.text
    kit = response.json()
    assert kit["application_id"] == ids["application_id"]

    version = kit["resume_version"]
    assert version["id"] == ids["version_id"]
    assert version["label"] == "Initech v1"
    assert version["template_id"] == "classic"
    assert version["score_before"] == 62.0
    assert version["score_after"] == 81.0
    assert version["missing_terms"] == ["Kafka"]
    assert version["pdf_url"].startswith("https://storage.example.test/documents/")
    assert version["docx_url"] is None

    cover = kit["cover_letter"]
    assert cover["tone"] == "standard"
    assert cover["body_markdown"] == "I built the thing at Acme."
    assert cover["claims"]["passed"] is True
    assert cover["claims"]["claims_checked"] == 3
    assert cover["claims"]["violations"] == []
    assert cover["pdf_url"] is None

    kinds = {followup["kind"] for followup in kit["followups"]}
    assert kinds == {"post_apply", "checkin"}


async def test_application_kit_detail_missing_application(client: AsyncClient) -> None:
    response = await client.get(f"/applications/{uuid.uuid4()}/kit")
    assert response.status_code == 404


async def test_list_and_get_job_targets(client: AsyncClient) -> None:
    response = await client.post("/users", json={"email": "jt-list@example.com"})
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]

    response = await client.post(
        f"/users/{user_id}/job-targets",
        json={"raw_description": "Backend role.", "company": "Globex", "title": "Engineer"},
    )
    assert response.status_code == 201, response.text
    job_target_id = response.json()["id"]

    response = await client.get(f"/users/{user_id}/job-targets")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == job_target_id
    assert row["company"] == "Globex"
    assert row["has_requirements"] is False
    assert row["has_kit"] is False
    # The list item is lightweight: no raw_description body.
    assert "raw_description" not in row

    response = await client.get(f"/job-targets/{job_target_id}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["raw_description"] == "Backend role."
    assert detail["extracted_requirements"] is None


async def test_get_job_target_missing(client: AsyncClient) -> None:
    response = await client.get(f"/job-targets/{uuid.uuid4()}")
    assert response.status_code == 404
