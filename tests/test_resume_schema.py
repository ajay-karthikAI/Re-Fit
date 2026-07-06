import pytest
from pydantic import ValidationError

from app.schemas.resume import ExperienceItem, StructuredResume


@pytest.fixture
def full_resume() -> StructuredResume:
    return StructuredResume(
        contact={
            "full_name": "Ada Lovelace",
            "email": "ada@example.com",
            "phone": "+1 555 010 2030",
            "location": "London, UK",
            "linkedin_url": "https://www.linkedin.com/in/ada",
            "github_url": "https://github.com/ada",
            "portfolio_url": "https://ada.dev/",
        },
        summary="Backend engineer focused on data platforms and developer tooling.",
        experience=[
            {
                "company": "Analytical Engines Ltd",
                "title": "Senior Software Engineer",
                "location": "London, UK",
                "start_date": "2021-03",
                "end_date": None,
                "bullets": [
                    "Designed an async ingestion pipeline processing 2M records/day.",
                    "Led migration from Python 3.9 to 3.12 across 14 services.",
                ],
                "technologies": ["Python", "FastAPI", "PostgreSQL"],
            },
            {
                "company": "Difference Corp",
                "title": "Software Engineer",
                "location": None,
                "start_date": "2018-06",
                "end_date": "2021-02",
                "bullets": ["Built internal billing reconciliation service."],
                "technologies": [],
            },
        ],
        education=[
            {
                "institution": "University of London",
                "degree": "BSc",
                "field": "Mathematics",
                "graduation_date": "2018-05",
                "details": ["First-class honours"],
            }
        ],
        skills=[
            {"category": "Languages", "items": ["Python", "SQL", "TypeScript"]},
            {"category": "Cloud", "items": ["AWS"]},
        ],
        projects=[
            {
                "name": "notation",
                "description": "A note-taking CLI.",
                "bullets": ["Published to PyPI with 3k downloads/month."],
                "technologies": ["Python", "Click"],
                "url": "https://github.com/ada/notation",
            }
        ],
    )


def test_round_trip_is_lossless(full_resume: StructuredResume) -> None:
    dumped = full_resume.model_dump_json()
    restored = StructuredResume.model_validate_json(dumped)
    assert restored == full_resume
    assert restored.model_dump_json() == dumped


def test_schema_version_defaults(full_resume: StructuredResume) -> None:
    assert full_resume.schema_version == "1.0"


def test_bad_date_format_rejected() -> None:
    with pytest.raises(ValidationError, match="YYYY-MM"):
        ExperienceItem(
            company="Acme",
            title="Engineer",
            start_date="March 2023",
            bullets=["Did things."],
        )


def test_invalid_month_rejected() -> None:
    with pytest.raises(ValidationError, match="YYYY-MM"):
        ExperienceItem(
            company="Acme",
            title="Engineer",
            start_date="2023-13",
            bullets=["Did things."],
        )


def test_end_date_before_start_date_rejected() -> None:
    with pytest.raises(ValidationError, match="must not be before"):
        ExperienceItem(
            company="Acme",
            title="Engineer",
            start_date="2023-05",
            end_date="2022-01",
            bullets=["Did things."],
        )


def test_empty_bullets_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 1"):
        ExperienceItem(
            company="Acme",
            title="Engineer",
            start_date="2023-05",
            bullets=[],
        )


def test_extra_field_rejected(full_resume: StructuredResume) -> None:
    data = full_resume.model_dump(mode="json")
    data["hallucinated_section"] = ["not in the source material"]
    with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs"):
        StructuredResume.model_validate(data)
