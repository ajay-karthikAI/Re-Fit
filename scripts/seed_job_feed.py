"""Seed the dev database with a Job Feed (Phase 4) that a person can click through
end to end — without any LLM calls at request time.

Builds on the fictional demo persona from ``scripts.seed`` / ``scripts.seed_dashboard``
and adds everything the Job Feed screen needs:

- three source boards with different health (healthy / degraded / dead) so the
  Source Boards settings page shows its color-coded badges
- postings ingested onto the healthy board, with pre-populated JD requirements so
  match scoring reuses the Phase 1 scorer locally (no LLM)
- a saved search against the persona's canonical profile, with real
  locally-computed match scores + missing_terms
- a persisted digest row for the digest-history view
- a *fully cached* application kit (tailored resume version + rendered PDF/DOCX +
  verified cover letter + PDF) for the first posting, whose ``source_url`` matches
  the posting — so the one-click "Generate kit" resolves to this cached kit and
  the kit view renders instantly with no LLM at request time.

Isolated from the demo dashboard user (its own email) so it never clobbers, and
is never clobbered by, ``scripts.seed_dashboard`` / ``scripts.seed_apply_kit``.

Requires Postgres + MinIO (`make up`). Run with:
uv run python -m scripts.seed_job_feed
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import dispose_engine, get_session_factory
from app.models import (
    CoverLetter,
    CoverLetterTone,
    Digest,
    Posting,
    Profile,
    SourceBoard,
    User,
)
from app.models.source_board import BoardHealth, SourceKind
from app.schemas.jd import JobRequirements, RequirementItem
from app.schemas.job_target import JobTargetCreate
from app.schemas.render import RenderRequest
from app.schemas.saved_search import SavedSearchCreate
from app.services import job_targets, profiles, saved_searches, users
from app.services.cover_letter import render_cover_letter_document
from app.services.digest import build_digest
from app.services.matching import refresh_matches_for_search
from app.services.postings import content_hash
from app.services.render import render_version_document
from app.services.score import score_resume
from app.services.score_cache import build_score_cache
from scripts.seed import CANONICAL_RESUME, JOB_TARGET
from scripts.seed_dashboard import (
    COVER_LETTER_BODY,
    REQUIREMENTS,
    _delete_demo_user,
    _verified_or_raise,
)

FEED_EMAIL = "jobfeed-demo@example.com"

# Greenhouse-shaped apply URL: detect_ats() reads it as greenhouse, and the
# kitted posting shares it so the one-click Generate-kit dedups onto the cached
# job target instead of spawning a fresh (LLM-requiring) one.
KITTED_URL = "https://boards.greenhouse.io/anthropic/jobs/4020"

# A second posting with no cached kit, so the feed shows more than one card with
# its own missing-terms chips. Its requirements are pre-populated too, so match
# scoring never reaches for the LLM.
SECOND_URL = "https://boards.greenhouse.io/anthropic/jobs/4088"
SECOND_DESCRIPTION = (
    "Research Engineer, Evals. Design and run rigorous evaluations for LLM "
    "systems: build eval harnesses, curate datasets, and quantify model quality "
    "regressions. Strong Python required; experience with distributed systems and "
    "statistics is a plus."
)
SECOND_REQUIREMENTS = JobRequirements(
    hard_skills=[
        RequirementItem(term="Python", weight=1.0, evidence="Strong Python required"),
        RequirementItem(term="evals", weight=1.0, evidence="run rigorous evaluations"),
        RequirementItem(term="eval harnesses", weight=0.9, evidence="build eval harnesses"),
        RequirementItem(term="statistics", weight=0.6, evidence="statistics is a plus"),
        RequirementItem(
            term="distributed systems", weight=0.6, evidence="distributed systems ... is a plus"
        ),
    ],
    soft_skills=[],
    domain_terms=["LLM systems", "model quality"],
    seniority="mid",
    must_haves=["Strong Python"],
    nice_to_haves=["distributed systems", "statistics"],
)


async def _build_cached_kit(session: AsyncSession, user: User, profile: Profile) -> None:
    """Recreate scripts.seed_dashboard's complete-kit build for the feed user, on a
    Greenhouse-shaped job target whose URL matches the kitted posting."""
    job_target = await job_targets.create_job_target(
        session,
        user.id,
        JobTargetCreate(
            company=JOB_TARGET.company,
            title=JOB_TARGET.title,
            source_url=KITTED_URL,
            raw_description=JOB_TARGET.raw_description,
        ),
    )
    job_target.extracted_requirements = REQUIREMENTS.model_dump(mode="json")
    await session.commit()

    version = await profiles.create_version(
        session, profile.id, job_target.id, label="Anthropic Applied AI v1"
    )
    tailored = CANONICAL_RESUME.model_copy(deep=True)
    # Fixture "tailoring": surface the ML skill group first. No new facts.
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
    await render_version_document(session, version.id, RenderRequest(format="docx"))

    source_jd = "\n".join(
        [f"Company: {JOB_TARGET.company}", f"Role: {JOB_TARGET.title}", JOB_TARGET.raw_description]
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


async def _board(
    session: AsyncSession,
    user: User,
    *,
    identifier: str,
    company: str,
    health: BoardHealth,
    failures: int,
    last_success_days_ago: int | None,
) -> SourceBoard:
    now = datetime.now(UTC)
    board = SourceBoard(
        user_id=user.id,
        source=SourceKind.greenhouse,
        identifier=identifier,
        company_name=company,
        health=health,
        consecutive_failures=failures,
        last_checked_at=now,
        last_success_at=(
            None if last_success_days_ago is None else now - timedelta(days=last_success_days_ago)
        ),
    )
    session.add(board)
    await session.commit()
    return board


async def _posting(
    session: AsyncSession,
    board: SourceBoard,
    *,
    external_id: str,
    title: str,
    url: str,
    description: str,
    requirements: JobRequirements,
    location: str,
    department: str,
    posted_days_ago: int,
) -> Posting:
    now = datetime.now(UTC)
    posting = Posting(
        source_board_id=board.id,
        external_id=external_id,
        title=title,
        location=location,
        department=department,
        url=url,
        description_text=description,
        posted_at=now - timedelta(days=posted_days_ago),
        content_hash=content_hash(title, description),
        first_seen_at=now,
        last_seen_at=now,
        extracted_requirements=requirements.model_dump(mode="json"),
    )
    session.add(posting)
    await session.commit()
    return posting


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        existing = (
            await session.execute(select(User).where(User.email == FEED_EMAIL))
        ).scalar_one_or_none()
        if existing is not None:
            await _delete_demo_user(session, existing)

        user = await users.create_user(session, FEED_EMAIL)
        profile = await profiles.upsert_canonical_profile(session, user.id, CANONICAL_RESUME)

        # A complete, cached kit for the first posting's job target.
        await _build_cached_kit(session, user, profile)

        # Three boards with distinct health so the settings page shows its badges.
        healthy = await _board(
            session,
            user,
            identifier="anthropic",
            company="Anthropic",
            health=BoardHealth.healthy,
            failures=0,
            last_success_days_ago=0,
        )
        await _board(
            session,
            user,
            identifier="acmeai",
            company="Acme AI",
            health=BoardHealth.degraded,
            failures=3,
            last_success_days_ago=2,
        )
        await _board(
            session,
            user,
            identifier="deadco",
            company="DeadCo",
            health=BoardHealth.dead,
            failures=9,
            last_success_days_ago=14,
        )

        kitted_posting = await _posting(
            session,
            healthy,
            external_id="4020",
            title=JOB_TARGET.title,
            url=KITTED_URL,
            description=JOB_TARGET.raw_description,
            requirements=REQUIREMENTS,
            location="San Francisco, CA",
            department="Applied AI",
            posted_days_ago=3,
        )
        await _posting(
            session,
            healthy,
            external_id="4088",
            title="Research Engineer, Evals",
            url=SECOND_URL,
            description=SECOND_DESCRIPTION,
            requirements=SECOND_REQUIREMENTS,
            location="Remote",
            department="Research",
            posted_days_ago=1,
        )

        # A saved search + real, locally-computed match scores (no LLM: the
        # postings already carry extracted_requirements). min_score kept low so
        # both postings clear the bar and the feed is populated.
        saved_search = await saved_searches.create_saved_search(
            session,
            SavedSearchCreate(
                user_id=user.id,
                name="AI/ML engineering roles",
                profile_id=profile.id,
                min_score=50.0,
            ),
        )
        stats = await refresh_matches_for_search(session, saved_search)

        # Persist a digest row for the digest-history view (build_digest only
        # computes; send_daily_digests is what normally persists — mirror that).
        digest = await build_digest(session, saved_search)
        session.add(
            Digest(
                saved_search_id=saved_search.id,
                new_match_count=digest.count,
                posting_ids=[str(m.posting_id) for m in digest.new_matches],
            )
        )
        await session.commit()

        print(
            json.dumps(
                {
                    "user_id": str(user.id),
                    "profile_id": str(profile.id),
                    "saved_search_id": str(saved_search.id),
                    "kitted_posting_id": str(kitted_posting.id),
                    "kitted_posting_title": kitted_posting.title,
                    "matches_computed": stats.computed,
                    "digest_new_matches": digest.count,
                },
                indent=2,
            )
        )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
