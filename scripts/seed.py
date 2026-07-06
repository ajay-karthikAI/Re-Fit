"""Seed the dev database with a demo user, canonical profile, job target,
resume version, and one application in status "applied".

Idempotent: re-running deletes and recreates the demo user (and, via FK
cascades, everything hanging off it).

Run with: uv run python -m scripts.seed
"""

import asyncio
import json

from sqlalchemy import select

from app.db import dispose_engine, get_session_factory
from app.models import User
from app.models.application import ApplicationStatus
from app.schemas.application import ApplicationCreate
from app.schemas.job_target import JobTargetCreate
from app.schemas.resume import StructuredResume
from app.services import applications, job_targets, profiles, users

DEMO_EMAIL = "demo@refit.local"

# Fixture data for a fictional demo persona. This is seed data for local
# development only — real profiles always come from the user's own material.
CANONICAL_RESUME = StructuredResume.model_validate(
    {
        "contact": {
            "full_name": "Maya Chen",
            "email": "maya.chen@example.com",
            "phone": "+1 415 555 0142",
            "location": "San Francisco, CA",
            "linkedin_url": "https://www.linkedin.com/in/maya-chen-demo",
            "github_url": "https://github.com/mayachen-demo",
        },
        "summary": (
            "ML engineer with 6 years building and shipping production ML systems: "
            "LLM-backed products, recommendation pipelines, and the serving "
            "infrastructure underneath them."
        ),
        "experience": [
            {
                "company": "Vector Labs",
                "title": "Senior Machine Learning Engineer",
                "location": "San Francisco, CA",
                "start_date": "2022-04",
                "end_date": None,
                "bullets": [
                    "Built a retrieval-augmented generation pipeline serving 40k queries/day with p95 latency under 800ms.",
                    "Cut LLM inference spend 35% by introducing prompt caching and routing easy queries to smaller models.",
                    "Designed offline/online eval harness for LLM outputs; caught 3 quality regressions before release.",
                    "Mentored two junior engineers through their first production model launches.",
                ],
                "technologies": ["Python", "PyTorch", "FastAPI", "PostgreSQL", "Redis", "AWS"],
            },
            {
                "company": "Streamline AI",
                "title": "Machine Learning Engineer",
                "location": "Remote",
                "start_date": "2019-07",
                "end_date": "2022-03",
                "bullets": [
                    "Owned the ranking model for the content feed (20M daily impressions), lifting CTR 12% over two quarters.",
                    "Migrated batch feature pipelines from cron scripts to Airflow, halving feature-freshness lag.",
                    "Deployed model serving on Kubernetes with canary rollouts and automated rollback.",
                ],
                "technologies": ["Python", "TensorFlow", "Airflow", "Kubernetes", "GCP"],
            },
        ],
        "education": [
            {
                "institution": "University of Washington",
                "degree": "MS",
                "field": "Computer Science",
                "graduation_date": "2019-06",
                "details": ["Thesis: efficient fine-tuning of transformer language models"],
            }
        ],
        "skills": [
            {"category": "Languages", "items": ["Python", "SQL", "Go"]},
            {
                "category": "ML",
                "items": ["PyTorch", "TensorFlow", "scikit-learn", "LLM fine-tuning"],
            },
            {
                "category": "Infrastructure",
                "items": ["AWS", "GCP", "Kubernetes", "Airflow", "Redis"],
            },
        ],
        "projects": [
            {
                "name": "promptbench",
                "description": "Open-source harness for regression-testing LLM prompts.",
                "bullets": ["1.2k GitHub stars; used in CI by a dozen companies."],
                "technologies": ["Python"],
                "url": "https://github.com/mayachen-demo/promptbench",
            }
        ],
    }
)

JOB_TARGET = JobTargetCreate(
    company="Anthropic",
    title="Machine Learning Engineer, Applied AI",
    source_url="https://example.com/jobs/anthropic-applied-ai-mle",
    raw_description=(
        "We're looking for an ML engineer to build LLM-powered products end to end: "
        "prompt design, retrieval pipelines, evals, and the serving infrastructure "
        "behind them. Strong Python, experience shipping production ML systems, and "
        "familiarity with modern LLM tooling required. Experience with FastAPI, "
        "Postgres, and cloud infrastructure is a plus."
    ),
)


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        existing = (
            await session.execute(select(User).where(User.email == DEMO_EMAIL))
        ).scalar_one_or_none()
        if existing is not None:
            await session.delete(existing)
            await session.commit()

        user = await users.create_user(session, DEMO_EMAIL)
        profile = await profiles.upsert_canonical_profile(session, user.id, CANONICAL_RESUME)
        job_target = await job_targets.create_job_target(session, user.id, JOB_TARGET)
        version = await profiles.create_version(
            session, profile.id, job_target.id, label="Anthropic Applied AI v1"
        )
        application = await applications.create_application(
            session,
            user.id,
            ApplicationCreate(
                job_target_id=job_target.id,
                resume_version_id=version.id,
                status=ApplicationStatus.applied,
            ),
        )

        print(
            json.dumps(
                {
                    "user_id": str(user.id),
                    "profile_id": str(profile.id),
                    "job_target_id": str(job_target.id),
                    "resume_version_id": str(version.id),
                    "application_id": str(application.id),
                    "application_status": application.status,
                },
                indent=2,
            )
        )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
