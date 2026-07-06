from io import BytesIO
from typing import Any

import pymupdf
from docx import Document as DocxDocument
from httpx import AsyncClient
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, Profile, ResumeVersion, User
from app.schemas.render import RenderRequest
from app.schemas.resume import StructuredResume
from app.services import render as render_service
from app.services.extract import extract_text


def _resume(*, bullet_count: int = 4) -> StructuredResume:
    bullets = [
        "Designed Python APIs for billing workflows with durable validation and monitoring.",
        "Improved PostgreSQL query performance for customer-facing account dashboards.",
        "Led incident reviews and documented follow-up work for production services.",
        "Built deployment automation for repeatable backend service releases.",
    ]
    if bullet_count > len(bullets):
        bullets.extend(
            f"Delivered backend platform improvement {index} with testing, rollout notes, and support docs."
            for index in range(len(bullets), bullet_count)
        )

    return StructuredResume(
        contact={
            "full_name": "Ada Example",
            "email": "ada@example.com",
            "phone": "+1 555 010 2030",
            "location": "Austin, TX",
            "linkedin_url": "https://www.linkedin.com/in/ada-example",
        },
        summary="Backend engineer focused on data platforms and reliable service operations.",
        experience=[
            {
                "company": "Acme Systems",
                "title": "Senior Software Engineer",
                "location": "Austin, TX",
                "start_date": "2021-01",
                "end_date": None,
                "bullets": bullets,
                "technologies": ["Python", "PostgreSQL", "FastAPI"],
            }
        ],
        education=[
            {
                "institution": "State University",
                "degree": "BS",
                "field": "Computer Science",
                "graduation_date": "2020-05",
                "details": ["Graduated with honors."],
            }
        ],
        skills=[
            {"category": "Languages", "items": ["Python", "SQL", "TypeScript"]},
            {"category": "Systems", "items": ["PostgreSQL", "FastAPI", "AWS"]},
        ],
        projects=[
            {
                "name": "ops-check",
                "description": "Operational checklist service.",
                "bullets": ["Built CLI reporting for production readiness reviews."],
                "technologies": ["Python"],
            }
        ],
    )


def _page_count(pdf_bytes: bytes) -> int:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        return doc.page_count


def _bullet_match_rate(resume: StructuredResume, pdf_bytes: bytes) -> float:
    extracted = extract_text(pdf_bytes, "resume.pdf").raw_text.lower()
    bullets = [bullet for item in resume.experience for bullet in item.bullets]
    bullets.extend(bullet for project in resume.projects for bullet in project.bullets)
    matched = sum(1 for bullet in bullets if fuzz.partial_ratio(bullet.lower(), extracted) >= 90)
    return matched / len(bullets)


def test_classic_pdf_round_trip_recovers_bullets() -> None:
    resume = _resume()

    pdf_bytes = render_service.render_pdf(resume)

    assert _page_count(pdf_bytes) in {1, 2}
    assert _bullet_match_rate(resume, pdf_bytes) >= 0.95


def test_docx_opens_and_contains_section_headings() -> None:
    docx_bytes = render_service.render_docx(_resume())
    doc = DocxDocument(BytesIO(docx_bytes))
    text = "\n".join(paragraph.text for paragraph in doc.paragraphs)

    for heading in ["SUMMARY", "EXPERIENCE", "EDUCATION", "SKILLS", "PROJECTS"]:
        assert heading in text


def test_pdf_autofit_warns_for_oversized_resume() -> None:
    result = render_service.render_pdf_result(_resume(bullet_count=90))

    assert result.warnings
    assert result.font_size is not None
    assert result.font_size <= 10.5 or result.page_count > 2


async def test_render_endpoint_stores_document_and_returns_presigned_url(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: Any,
) -> None:
    stored: dict[str, Any] = {}

    def fake_put_object(key: str, body: bytes, content_type: str) -> None:
        stored["key"] = key
        stored["body"] = body
        stored["content_type"] = content_type

    def fake_presigned_get_url(key: str, expires_in: int = 900) -> str:
        return f"https://storage.example.test/{key}?expires={expires_in}"

    monkeypatch.setattr(render_service.storage, "put_object", fake_put_object)
    monkeypatch.setattr(render_service.storage, "presigned_get_url", fake_presigned_get_url)

    user = User(email="render-endpoint@example.com")
    session.add(user)
    await session.flush()
    profile = Profile(user_id=user.id, data=_resume().model_dump(mode="json"), is_canonical=True)
    session.add(profile)
    await session.flush()
    version = ResumeVersion(profile_id=profile.id, data=profile.data, label="render me")
    session.add(version)
    await session.commit()

    response = await client.post(
        f"/versions/{version.id}/render",
        json=RenderRequest(format="pdf").model_dump(mode="json"),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["download_url"].startswith("https://storage.example.test/")
    assert stored["key"] == f"documents/{user.id}/{version.id}/resume_pdf.pdf"
    assert stored["content_type"] == "application/pdf"
    assert stored["body"].startswith(b"%PDF")

    rows = (
        (await session.execute(select(Document).where(Document.resume_version_id == version.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].s3_key == stored["key"]
