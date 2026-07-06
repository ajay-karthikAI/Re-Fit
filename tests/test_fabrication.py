from app.schemas.jd import JobRequirements, RequirementItem
from app.schemas.resume import StructuredResume
from app.services.claims import verify_prose, verify_rewrite


def _requirements() -> JobRequirements:
    return JobRequirements(
        hard_skills=[
            RequirementItem(
                term="Python",
                weight=1.0,
                evidence="Expert-level Python",
            ),
            RequirementItem(
                term="Kubernetes",
                weight=0.9,
                evidence="Experience with Kubernetes",
            ),
        ],
        soft_skills=[],
        domain_terms=["billing"],
        seniority="senior",
        must_haves=["Expert-level Python"],
        nice_to_haves=["Kubernetes"],
    )


def _profile() -> StructuredResume:
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
                    "Built REST APIs in Python for Acme.",
                    "Reduced p99 latency from 900ms to 210ms.",
                ],
                "technologies": ["Python", "FastAPI"],
            }
        ],
        education=[],
        skills=[{"category": "Languages", "items": ["Python", "SQL"]}],
        projects=[],
    )


def test_fabricated_number_is_rejected() -> None:
    profile = _profile()
    result = verify_rewrite(
        original="Built REST APIs in Python for Acme.",
        rewritten="Built REST APIs in Python for Acme, improving throughput by 40%.",
        profile=profile,
        requirements=_requirements(),
        parent_experience=profile.experience[0],
    )

    assert not result.passed
    assert any("introduced number" in reason for reason in result.reasons)


def test_fabricated_tech_is_rejected() -> None:
    profile = _profile()
    result = verify_rewrite(
        original="Built REST APIs in Python for Acme.",
        rewritten="Built Kubernetes-backed REST APIs in Python for Acme.",
        profile=profile,
        requirements=_requirements(),
        parent_experience=profile.experience[0],
    )

    assert not result.passed
    assert any("unbacked tech" in reason for reason in result.reasons)


def test_changed_employer_is_rejected() -> None:
    profile = _profile()
    result = verify_rewrite(
        original="Built REST APIs in Python for Acme.",
        rewritten="Built REST APIs in Python for Globex.",
        profile=profile,
        requirements=_requirements(),
        parent_experience=profile.experience[0],
    )

    assert not result.passed
    assert any("employer/title/date" in reason for reason in result.reasons)


def test_honest_rephrasings_pass() -> None:
    profile = _profile()
    requirements = _requirements()

    api_result = verify_rewrite(
        original="Built REST APIs in Python for Acme.",
        rewritten="Built Python REST APIs for Acme.",
        profile=profile,
        requirements=requirements,
        parent_experience=profile.experience[0],
    )
    latency_result = verify_rewrite(
        original="Reduced p99 latency from 900ms to 210ms.",
        rewritten="Reduced p99 quote latency from 900ms to 210ms.",
        profile=profile,
        requirements=requirements,
        parent_experience=profile.experience[0],
    )

    assert api_result.passed, api_result.reasons
    assert latency_result.passed, latency_result.reasons


def test_prose_fabricated_team_size_is_rejected() -> None:
    profile = _profile()
    raw_jd = "Acme is hiring for Python API work."

    result = verify_prose(
        "Dear Acme team,\n\nAt Acme, I led a team of 12 while building REST APIs in Python.",
        profile,
        raw_jd,
    )

    assert not result.passed
    assert any("unsupported number: 12" in violation for violation in result.violations)


def test_prose_fabricated_company_praise_is_rejected() -> None:
    profile = _profile()
    raw_jd = "Acme is hiring for Python API work."

    result = verify_prose(
        "Dear Acme team,\n\nYour Series C momentum makes this API role compelling.",
        profile,
        raw_jd,
    )

    assert not result.passed
    assert any("Series" in violation for violation in result.violations)
