import numpy as np
import pytest
from pytest import MonkeyPatch

from app.schemas.jd import JobRequirements, RequirementItem
from app.schemas.resume import StructuredResume
from app.services import render as render_service
from app.services import score as score_service
from app.services.templates import list_template_specs

TEMPLATE_IDS = [spec.id for spec in list_template_specs()]


def _zero_embed(texts: list[str]) -> np.ndarray:
    return np.zeros((len(texts), 3), dtype=np.float32)


def _requirements(*, include_terms: bool = True) -> JobRequirements:
    hard_skills = (
        [
            RequirementItem(term="Python", weight=1.0, evidence="Python"),
            RequirementItem(term="Kubernetes", weight=0.8, evidence="Kubernetes"),
        ]
        if include_terms
        else []
    )
    return JobRequirements(
        hard_skills=hard_skills,
        soft_skills=[],
        domain_terms=[],
        seniority="senior",
        must_haves=[],
        nice_to_haves=[],
    )


def _resume(
    *,
    education: bool = True,
    skills: list[str] | None = None,
    bullets: list[str] | None = None,
) -> StructuredResume:
    return StructuredResume(
        contact={"full_name": "Ada Example", "email": "ada@example.com"},
        summary="Backend engineer.",
        experience=[
            {
                "company": "Acme",
                "title": "Senior Software Engineer",
                "start_date": "2021-01",
                "end_date": None,
                "bullets": bullets
                or [
                    "Built Python APIs for internal billing workflows.",
                    "Improved observability for production services.",
                    "Partnered with product managers on launch planning.",
                ],
                "technologies": ["Python"],
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
        ]
        if education
        else [],
        skills=[{"category": "Languages", "items": ["Python", "SQL"] if skills is None else skills}]
        if skills != []
        else [],
        projects=[],
    )


def test_keyword_coverage_reports_missing_kubernetes(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(score_service, "_embed_texts", _zero_embed)

    score = score_service.score_resume(_resume(), _requirements())

    assert "Python" in score.keyword_coverage.covered_terms
    assert "Kubernetes" in score.keyword_coverage.missing_terms
    assert score.keyword_coverage.score < 100


def test_section_integrity_penalizes_missing_sections() -> None:
    score = score_service.score_resume(
        _resume(education=False, skills=[]),
        _requirements(include_terms=False),
    )

    failed = {check.name for check in score.section_integrity.checks if not check.passed}
    assert {"education", "skills"} <= failed
    assert score.section_integrity.score < 100


def test_format_health_is_populated_by_default_renderer() -> None:
    score = score_service.score_resume(_resume(), _requirements(include_terms=False))
    component = next(item for item in score.components if item.name == "format_health")

    assert score.format_health.score is not None
    assert score.format_health.renderer_available
    assert component.included
    assert component.weighted_points is not None


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_format_health_round_trip_survives_all_templates(template_id: str) -> None:
    score = score_service.score_resume(
        _resume(),
        _requirements(include_terms=False),
        renderer=render_service.TemplateResumeRenderer(template_id),  # type: ignore[arg-type]
    )

    assert score.format_health.match_rate is not None
    assert score.format_health.match_rate >= 0.95
    assert score.format_health.score == 100.0


def test_four_page_resume_is_length_penalized() -> None:
    long_bullets = [
        "Designed reliable backend services for internal teams with careful testing and rollout plans."
        for _ in range(120)
    ]

    score = score_service.score_resume(
        _resume(bullets=long_bullets),
        _requirements(include_terms=False),
    )

    assert score.length_and_density.estimated_pages == 4
    assert score.length_and_density.score < 75
    assert any("4 pages" in note for note in score.length_and_density.notes)


def test_score_resume_is_deterministic(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(score_service, "_embed_texts", _zero_embed)
    resume = _resume()
    requirements = _requirements()

    first = score_service.score_resume(resume, requirements).model_dump(mode="json")
    second = score_service.score_resume(resume, requirements).model_dump(mode="json")

    assert first == second
