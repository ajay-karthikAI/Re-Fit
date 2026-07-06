"""Seed a demo user whose Apply Kit screen is fully assembled — without any LLM
calls at request time.

The apply-kit endpoint generates missing pieces inline (tailoring, rendering,
short answers). To make the screen load instantly and deterministically for
dogfooding/screenshots, this pre-builds every cached piece:

- a Greenhouse job target (source_url on boards.greenhouse.io -> source_ats)
- a tailored resume version with real before/after ATS scores + rendered PDF
- a cover letter (verify_prose-checked) + rendered PDF
- a near-complete answer profile (referral source left blank, to show the gap)
- the "why do you want to work here?" short answer, grounded and verified

Requires Postgres + MinIO (`make up`). Run with:
uv run python -m scripts.seed_apply_kit
"""

import asyncio
import json

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.ats_fields import FIELD_TAXONOMY
from app.db import dispose_engine, get_session_factory
from app.models import (
    CoverLetter,
    CoverLetterTone,
    Document,
    JobTarget,
    Profile,
    ResumeVersion,
    ShortAnswer,
    User,
)
from app.models.short_answer import ShortAnswerKind, hash_question
from app.schemas.answer_profile import AnswerProfileWrite
from app.schemas.job_target import JobTargetCreate
from app.schemas.render import RenderRequest
from app.services import answer_profile, job_targets, profiles, users
from app.services.claims import verify_prose
from app.services.cover_letter import render_cover_letter_document
from app.services.render import render_version_document
from app.services.score import score_resume
from app.services.score_cache import build_score_cache
from scripts.seed import CANONICAL_RESUME
from scripts.seed_dashboard import COVER_LETTER_BODY, REQUIREMENTS

APPLY_EMAIL = "apply-demo@example.com"

JOB_TARGET = JobTargetCreate(
    company="Anthropic",
    title="Machine Learning Engineer, Applied AI",
    source_url="https://boards.greenhouse.io/anthropic/jobs/4020693008",
    raw_description=(
        "We're looking for an ML engineer to build LLM-powered products end to end: "
        "prompt design, retrieval pipelines, evals, and the serving infrastructure "
        "behind them. Strong Python, experience shipping production ML systems, and "
        "familiarity with modern LLM tooling required. Experience with FastAPI, "
        "Postgres, and cloud infrastructure is a plus."
    ),
)

# Grounded answer to the fixed Greenhouse "why" question. Every fact is present
# in CANONICAL_RESUME or the JD; verify_prose enforces this at seed time.
WHY_COMPANY_ANSWER = (
    "This role is about building LLM-powered products end to end — prompt design, "
    "retrieval pipelines, evals, and the serving infrastructure behind them — which "
    "is exactly the work I do. At Vector Labs I built a retrieval-augmented generation "
    "pipeline serving 40k queries/day with p95 latency under 800ms and designed the "
    "eval harness that caught 3 quality regressions before release. That direct "
    "overlap with production LLM systems is why this role stands out to me."
)

ANSWER_PROFILE = AnswerProfileWrite(
    work_auth="citizen",
    sponsorship_needed=False,
    salary_min=185000,
    salary_max=225000,
    salary_currency="USD",
    salary_type="annual",
    relocation="no",
    notice_period_days=21,
    pronouns="she/her",
    referral_source_default=None,  # left blank on purpose, to show the gap banner
    eeo_prefs=None,
)


async def _delete_existing(session: AsyncSession, user: User) -> None:
    version_ids = (
        select(ResumeVersion.id)
        .join(Profile, ResumeVersion.profile_id == Profile.id)
        .where(Profile.user_id == user.id)
    )
    job_target_ids = select(JobTarget.id).where(JobTarget.user_id == user.id)
    await session.execute(
        delete(ShortAnswer).where(ShortAnswer.job_target_id.in_(job_target_ids))
    )
    await session.execute(delete(CoverLetter).where(CoverLetter.resume_version_id.in_(version_ids)))
    await session.execute(delete(Document).where(Document.resume_version_id.in_(version_ids)))
    await session.execute(delete(ResumeVersion).where(ResumeVersion.id.in_(version_ids)))
    await session.execute(delete(JobTarget).where(JobTarget.user_id == user.id))
    await session.delete(user)  # cascades profiles + answer_profile
    await session.commit()


def _why_company_question() -> str:
    spec = next(s for s in FIELD_TAXONOMY["greenhouse"] if s.key == "why_company")
    return spec.label


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        existing = (
            await session.execute(select(User).where(User.email == APPLY_EMAIL))
        ).scalar_one_or_none()
        if existing is not None:
            await _delete_existing(session, existing)

        user = await users.create_user(session, APPLY_EMAIL)
        profile = await profiles.upsert_canonical_profile(session, user.id, CANONICAL_RESUME)

        job_target = await job_targets.create_job_target(session, user.id, JOB_TARGET)
        assert job_target.source_ats == "greenhouse", job_target.source_ats
        job_target.extracted_requirements = REQUIREMENTS.model_dump(mode="json")
        await session.commit()

        # Tailored version: fixture "tailoring" reorders skills (no new facts).
        version = await profiles.create_version(
            session, profile.id, job_target.id, label="Anthropic Applied AI v1"
        )
        tailored = CANONICAL_RESUME.model_copy(deep=True)
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

        await render_version_document(session, version.id, RenderRequest(format="pdf"))

        source_jd = "\n".join(
            [f"Company: {JOB_TARGET.company}", f"Role: {JOB_TARGET.title}", JOB_TARGET.raw_description]
        )
        cover_report = verify_prose(COVER_LETTER_BODY, CANONICAL_RESUME, source_jd)
        if not cover_report.passed:
            raise RuntimeError(f"seed cover letter failed verification: {cover_report.violations}")
        cover = CoverLetter(
            job_target_id=job_target.id,
            resume_version_id=version.id,
            body_markdown=COVER_LETTER_BODY,
            tone=CoverLetterTone.standard,
            word_count=len(COVER_LETTER_BODY.split()),
            claim_report=cover_report.model_dump(mode="json"),
        )
        session.add(cover)
        await session.commit()
        await session.refresh(cover)
        await render_cover_letter_document(session, cover.id, RenderRequest(format="pdf"))

        await answer_profile.upsert_answer_profile(session, user.id, ANSWER_PROFILE)

        # The "why" short answer, grounded against the tailored resume + JD.
        why_report = verify_prose(WHY_COMPANY_ANSWER, tailored, JOB_TARGET.raw_description)
        if not why_report.passed:
            raise RuntimeError(f"seed short answer failed verification: {why_report.violations}")
        question = _why_company_question()
        session.add(
            ShortAnswer(
                job_target_id=job_target.id,
                question=question,
                question_hash=hash_question(question),
                answer_markdown=WHY_COMPANY_ANSWER,
                question_kind=ShortAnswerKind.why_company,
                claim_report=why_report.model_dump(mode="json"),
            )
        )
        await session.commit()

        print(
            json.dumps(
                {
                    "user_id": str(user.id),
                    "job_target_id": str(job_target.id),
                    "source_ats": job_target.source_ats,
                    "score_before": score_before.headline_score,
                    "score_after": score_after.headline_score,
                },
                indent=2,
            )
        )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
