from app.schemas.resume import StructuredResume
from app.services.diffing import diff_structured_resumes


def _resume() -> StructuredResume:
    return StructuredResume(
        contact={"full_name": "Ada Example", "email": "ada@example.com"},
        summary="Backend engineer.",
        experience=[
            {
                "company": "Acme",
                "title": "Senior Software Engineer",
                "start_date": "2021-01",
                "end_date": None,
                "bullets": [
                    "Built Python APIs for internal billing workflows.",
                    "Improved PostgreSQL query performance.",
                ],
                "technologies": ["Python", "PostgreSQL"],
            }
        ],
        education=[
            {
                "institution": "State University",
                "degree": "BS",
                "field": "Computer Science",
                "graduation_date": "2020-05",
                "details": [],
            }
        ],
        skills=[{"category": "Languages", "items": ["Python", "SQL"]}],
        projects=[],
    )


def test_identical_resumes_have_empty_diff() -> None:
    resume = _resume()

    assert diff_structured_resumes(resume, resume.model_copy(deep=True)) == []


def test_known_bullet_mutation_has_expected_ref() -> None:
    before = _resume()
    after = before.model_copy(deep=True)
    after.experience[0].bullets[1] = "Tuned PostgreSQL queries for account dashboards."

    diff = diff_structured_resumes(before, after)

    assert [entry.model_dump(mode="json") for entry in diff] == [
        {
            "bullet_ref": "/experience/0/bullets/1",
            "before": "Improved PostgreSQL query performance.",
            "after": "Tuned PostgreSQL queries for account dashboards.",
            "requirement_targeted": None,
        }
    ]
