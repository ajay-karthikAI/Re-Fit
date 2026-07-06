"""Seed the dev database with a demo user whose dashboard shows a complete
application kit — without any LLM calls.

Builds on scripts.seed's fictional demo persona and adds everything the
tracker displays:

- extracted requirements (hand-built fixture, JD-sourced terms only)
- a tailored resume version with real locally-computed before/after ATS scores
- rendered resume PDF + DOCX and cover letter PDF in MinIO
- a fixture cover letter whose claim report comes from the real verify_prose
- two follow-ups (one overdue) scheduled from applied_at
- a second draft application with no kit pieces, for the status filter chips

All prose is fixture content for the fictional persona and references only
facts present in the fixture resume / job description; verify_prose must pass
or seeding aborts.

Requires Postgres + MinIO (`make up`). Run with:
uv run python -m scripts.seed_dashboard
"""

import asyncio
from datetime import UTC, datetime, timedelta
import json

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import dispose_engine, get_session_factory
from app.models import (
    Application,
    CoverLetter,
    CoverLetterTone,
    Document,
    Followup,
    FollowupKind,
    JobTarget,
    PipelineRun,
    Profile,
    ResumeVersion,
    User,
)
from app.models.application import ApplicationStatus
from app.schemas.application import ApplicationCreate
from app.schemas.jd import JobRequirements, RequirementItem
from app.schemas.job_target import JobTargetCreate
from app.schemas.render import RenderRequest
from app.schemas.resume import StructuredResume
from app.services import applications, job_targets, profiles, users
from app.services.claims import verify_prose
from app.services.cover_letter import render_cover_letter_document
from app.services.followup import add_business_days
from app.services.render import render_version_document
from app.services.score import score_resume
from app.services.score_cache import build_score_cache
from scripts.seed import CANONICAL_RESUME, DEMO_EMAIL, JOB_TARGET

REQUIREMENTS = JobRequirements(
    hard_skills=[
        RequirementItem(term="Python", weight=1.0, evidence="Strong Python"),
        RequirementItem(
            term="retrieval pipelines",
            weight=0.9,
            evidence="prompt design, retrieval pipelines, evals",
        ),
        RequirementItem(term="evals", weight=0.85, evidence="retrieval pipelines, evals"),
        RequirementItem(term="FastAPI", weight=0.7, evidence="Experience with FastAPI"),
        RequirementItem(term="Postgres", weight=0.7, evidence="Experience with ... Postgres"),
        RequirementItem(
            term="cloud infrastructure",
            weight=0.6,
            evidence="cloud infrastructure is a plus",
        ),
        RequirementItem(
            term="prompt design",
            weight=0.8,
            evidence="prompt design, retrieval pipelines, evals",
        ),
    ],
    soft_skills=[],
    domain_terms=["LLM tooling", "serving infrastructure"],
    seniority="senior",
    must_haves=["Strong Python, experience shipping production ML systems"],
    nice_to_haves=["Experience with FastAPI, Postgres, and cloud infrastructure"],
)

# Fixture prose for the fictional demo persona. Every fact below is present in
# scripts.seed.CANONICAL_RESUME or the fixture JD; verify_prose enforces this.
COVER_LETTER_BODY = """\
I'm writing to apply for the Machine Learning Engineer, Applied AI role at Anthropic. \
The posting describes building LLM-powered products end to end: prompt design, retrieval \
pipelines, evals, and the serving infrastructure behind them. That is the work I do today.

At Vector Labs I built a retrieval-augmented generation pipeline serving 40k queries/day \
with p95 latency under 800ms, and cut LLM inference spend 35% by introducing prompt caching \
and routing easy queries to smaller models. I also designed the offline/online eval harness \
for LLM outputs, which caught 3 quality regressions before release.

Before that, at Streamline AI, I owned the ranking model for a content feed with 20M daily \
impressions and deployed model serving on Kubernetes with canary rollouts and automated \
rollback.

I'd welcome the chance to talk about how this experience maps to the role."""

POST_APPLY_FOLLOWUP = {
    "subject": "Following up: Machine Learning Engineer, Applied AI application",
    "body": """\
Hi,

I applied for the Machine Learning Engineer, Applied AI role at Anthropic and wanted to \
follow up. The posting asks for experience shipping production ML systems; at Vector Labs \
I built a retrieval-augmented generation pipeline serving 40k queries/day with p95 latency \
under 800ms, together with the eval harness used to catch regressions before release.

I remain very interested in the role and am happy to share more detail whenever useful.

Best,
Maya Chen""",
}

CHECKIN_FOLLOWUP = {
    "subject": "Checking in: Machine Learning Engineer, Applied AI",
    "body": """\
Hi,

I wanted to check in on my application for the Machine Learning Engineer, Applied AI role. \
I understand hiring takes time; I remain interested and am glad to provide anything else \
that would help.

Best,
Maya Chen""",
}

DRAFT_JOB_TARGET = JobTargetCreate(
    company="Figma",
    title="ML Platform Engineer",
    source_url="https://example.com/jobs/figma-ml-platform",
    raw_description=(
        "Figma is hiring an ML Platform Engineer to build the training and serving "
        "platform used by product ML teams. Strong Python, Kubernetes, and experience "
        "operating model serving infrastructure required. Airflow and GCP are a plus."
    ),
)


def _verified_or_raise(body: str, profile: StructuredResume, source_jd: str, label: str) -> dict:
    report = verify_prose(body, profile, source_jd)
    if not report.passed:
        raise RuntimeError(f"seed {label} failed prose verification: {report.violations}")
    return report.model_dump(mode="json")


async def _delete_demo_user(session: AsyncSession, user: User) -> None:
    """Delete the demo user's graph in dependency order; not every FK cascades
    (resume_versions.job_target_id, cover_letters, followups)."""
    application_ids = select(Application.id).where(Application.user_id == user.id)
    version_ids = (
        select(ResumeVersion.id)
        .join(Profile, ResumeVersion.profile_id == Profile.id)
        .where(Profile.user_id == user.id)
    )
    await session.execute(delete(Followup).where(Followup.application_id.in_(application_ids)))
    await session.execute(delete(Application).where(Application.user_id == user.id))
    await session.execute(
        delete(CoverLetter).where(CoverLetter.resume_version_id.in_(version_ids))
    )
    await session.execute(delete(Document).where(Document.resume_version_id.in_(version_ids)))
    await session.execute(delete(ResumeVersion).where(ResumeVersion.id.in_(version_ids)))
    await session.execute(delete(PipelineRun).where(PipelineRun.user_id == user.id))
    await session.execute(delete(JobTarget).where(JobTarget.user_id == user.id))
    await session.delete(user)  # cascades: profiles, uploads, pipeline_runs
    await session.commit()


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        existing = (
            await session.execute(select(User).where(User.email == DEMO_EMAIL))
        ).scalar_one_or_none()
        if existing is not None:
            await _delete_demo_user(session, existing)

        user = await users.create_user(session, DEMO_EMAIL)
        profile = await profiles.upsert_canonical_profile(session, user.id, CANONICAL_RESUME)

        # --- Application 1: applied, with a complete kit ---------------------
        job_target = await job_targets.create_job_target(session, user.id, JOB_TARGET)
        job_target.extracted_requirements = REQUIREMENTS.model_dump(mode="json")
        await session.commit()

        version = await profiles.create_version(
            session, profile.id, job_target.id, label="Anthropic Applied AI v1"
        )
        tailored = CANONICAL_RESUME.model_copy(deep=True)
        # Fixture "tailoring": put the ML skill group first. No new facts.
        tailored.skills = [tailored.skills[1], tailored.skills[0], tailored.skills[2]]
        score_before = score_resume(CANONICAL_RESUME, REQUIREMENTS)
        score_after = score_resume(tailored, REQUIREMENTS)
        version.data = tailored.model_dump(mode="json")
        version.diff = {
            "changes": [],
            "stats": {"skills_reordered": True},
            "discarded_rewrites": [],
            "score_before": score_before.model_dump(mode="json"),
            "score_after": score_after.model_dump(mode="json"),
        }
        version.score_cache = build_score_cache(job_target.id, score_after)
        await session.commit()

        applied_at = datetime.now(UTC) - timedelta(days=10)
        application = await applications.create_application(
            session,
            user.id,
            ApplicationCreate(
                job_target_id=job_target.id,
                resume_version_id=version.id,
                status=ApplicationStatus.applied,
            ),
        )
        application.applied_at = applied_at
        await session.commit()

        await render_version_document(session, version.id, RenderRequest(format="pdf"))
        await render_version_document(session, version.id, RenderRequest(format="docx"))

        source_jd = "\n".join(
            [
                f"Company: {JOB_TARGET.company}",
                f"Role: {JOB_TARGET.title}",
                JOB_TARGET.raw_description,
            ]
        )
        cover = CoverLetter(
            job_target_id=job_target.id,
            resume_version_id=version.id,
            body_markdown=COVER_LETTER_BODY,
            tone=CoverLetterTone.standard,
            word_count=len(COVER_LETTER_BODY.split()),
            claim_report=_verified_or_raise(
                COVER_LETTER_BODY, CANONICAL_RESUME, source_jd, "cover letter"
            ),
        )
        session.add(cover)
        await session.commit()
        await session.refresh(cover)
        await render_cover_letter_document(session, cover.id, RenderRequest(format="pdf"))

        for kind, fixture, offset_days in (
            (FollowupKind.post_apply, POST_APPLY_FOLLOWUP, 5),
            (FollowupKind.checkin, CHECKIN_FOLLOWUP, 10),
        ):
            _verified_or_raise(
                f"{fixture['subject']}\n\n{fixture['body']}",
                CANONICAL_RESUME,
                source_jd,
                f"{kind.value} followup",
            )
            session.add(
                Followup(
                    application_id=application.id,
                    kind=kind,
                    subject=fixture["subject"],
                    body_markdown=fixture["body"],
                    send_after=add_business_days(applied_at.date(), offset_days),
                )
            )
        await session.commit()

        # --- Application 2: draft, no kit pieces yet --------------------------
        draft_target = await job_targets.create_job_target(session, user.id, DRAFT_JOB_TARGET)
        draft_version = await profiles.create_version(
            session, profile.id, draft_target.id, label="Figma ML Platform v1"
        )
        draft_application = await applications.create_application(
            session,
            user.id,
            ApplicationCreate(
                job_target_id=draft_target.id,
                resume_version_id=draft_version.id,
                status=ApplicationStatus.draft,
            ),
        )

        print(
            json.dumps(
                {
                    "user_id": str(user.id),
                    "applied_application_id": str(application.id),
                    "applied_version_id": str(version.id),
                    "score_before": score_before.headline_score,
                    "score_after": score_after.headline_score,
                    "cover_letter_id": str(cover.id),
                    "draft_application_id": str(draft_application.id),
                },
                indent=2,
            )
        )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
