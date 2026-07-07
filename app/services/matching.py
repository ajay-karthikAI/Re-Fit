"""Match ingested postings against saved searches by reusing Phase 1 scoring.

A job posting's description *is* a job description, so this module treats it
identically: the same ``extract_requirements`` LLM path from ``jd.py`` turns the
posting text into ``JobRequirements``, and the same deterministic
``score_resume`` from ``score.py`` scores the search's profile against them.
There is deliberately **no new scoring logic here** — only new inputs to the
existing scorer.

Two caches keep the expensive LLM path rare:

* ``posting.extracted_requirements`` — the extraction is cached on the posting,
  so re-scoring it against N saved searches costs at most one extraction, and
  the storage layer invalidates it when the posting text changes.
* ``posting_matches`` — a computed score is reused until the posting's
  ``content_hash`` or the search's ``profile_id`` changes.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import anyio.to_thread
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Posting, PostingMatch, Profile, SavedSearch, SourceBoard
from app.schemas.jd import JobRequirements
from app.schemas.resume import StructuredResume
from app.schemas.saved_search import MatchResult, PostingMatchRead, SearchFilters
from app.services.errors import NotFoundError
from app.services.jd import extract_requirements
from app.services.score import score_resume

logger = logging.getLogger(__name__)


def visible_board_condition(user_id: uuid.UUID):
    """The ownership invariant, as a reusable SQL predicate on ``SourceBoard``.

    A posting is visible to a saved search iff its ``source_board`` is either the
    search-owning user's own board **or** a system/seed board (``user_id IS
    NULL``, watched for everyone — see ``WATCHED_BOARDS.md``). This is an
    invariant applied everywhere matches are computed or listed, not an optional
    filter: any query that reaches ``posting_matches`` must join ``SourceBoard``
    and AND this in (see CLAUDE.md, Phase 4). Callers must join
    ``Posting.source_board_id == SourceBoard.id`` for this to bind.
    """
    return or_(SourceBoard.user_id == user_id, SourceBoard.user_id.is_(None))


@dataclass
class MatchRefreshStats:
    computed: int = 0
    """Matches (re)scored this run."""
    skipped: int = 0
    """Matches left as-is because neither the posting text nor the profile changed."""


async def _get_or_extract_requirements(session: AsyncSession, posting: Posting) -> JobRequirements:
    """Return the posting's JobRequirements, extracting (one LLM call) only on a
    cache miss and persisting the result on the posting row."""
    if posting.extracted_requirements is not None:
        return JobRequirements.model_validate(posting.extracted_requirements)

    # Deliberately no heuristic_fallback here: the service must not silently
    # approximate. With a placeholder key this raises MissingLLMCredentialsError.
    # A caller (an eval script/task) that wants the heuristic must pre-populate
    # posting.extracted_requirements via jd.extract_requirements(..., heuristic_fallback=True)
    # so the choice is explicit and lives with the caller, not buried here.
    requirements, _usage = await extract_requirements(posting.description_text)
    posting.extracted_requirements = requirements.model_dump(mode="json")
    await session.commit()
    return requirements


async def score_posting_for_search(
    session: AsyncSession, posting: Posting, saved_search: SavedSearch
) -> MatchResult:
    """Score one posting against one saved search's profile.

    Reuses the Phase 1 scorer wholesale: the headline ATS score becomes the
    match score and the keyword-coverage gaps become ``missing_terms``.
    """
    profile = await session.get(Profile, saved_search.profile_id)
    if profile is None:
        raise NotFoundError(f"profile {saved_search.profile_id} not found")

    requirements = await _get_or_extract_requirements(session, posting)
    resume = StructuredResume.model_validate(profile.data)
    score = await anyio.to_thread.run_sync(lambda: score_resume(resume, requirements))
    return MatchResult(
        score=score.headline_score,
        missing_terms=score.keyword_coverage.missing_terms,
    )


async def refresh_matches_for_search(
    session: AsyncSession, saved_search: SavedSearch
) -> MatchRefreshStats:
    """Ensure a cached match exists and is current for every active, canonical
    posting **within the search owner's visibility scope** (their own boards plus
    system/seed boards). Skips any whose ``content_hash`` and the search's
    ``profile_id`` already match the stored score, so unchanged postings cost
    nothing. Postings on boards owned by other users are never scored — the
    ownership invariant is enforced at the source, not just at read time."""
    stats = MatchRefreshStats()

    postings = (
        (
            await session.execute(
                select(Posting)
                .join(SourceBoard, Posting.source_board_id == SourceBoard.id)
                .where(
                    Posting.is_active.is_(True),
                    Posting.canonical_posting_id.is_(None),
                    visible_board_condition(saved_search.user_id),
                )
            )
        )
        .scalars()
        .all()
    )
    existing = {
        m.posting_id: m
        for m in (
            await session.execute(
                select(PostingMatch).where(PostingMatch.saved_search_id == saved_search.id)
            )
        )
        .scalars()
        .all()
    }

    for posting in postings:
        match = existing.get(posting.id)
        if (
            match is not None
            and match.scored_content_hash == posting.content_hash
            and match.scored_profile_id == saved_search.profile_id
        ):
            stats.skipped += 1
            continue

        result = await score_posting_for_search(session, posting, saved_search)
        if match is None:
            match = PostingMatch(posting_id=posting.id, saved_search_id=saved_search.id)
            session.add(match)
        match.score = result.score
        match.missing_terms = result.missing_terms
        match.scored_content_hash = posting.content_hash
        match.scored_profile_id = saved_search.profile_id
        match.computed_at = datetime.now(UTC)
        stats.computed += 1

    await session.commit()
    logger.info(
        "refreshed matches for search %s: computed=%d skipped=%d",
        saved_search.id,
        stats.computed,
        stats.skipped,
    )
    return stats


async def list_matches(session: AsyncSession, saved_search_id: uuid.UUID) -> list[PostingMatchRead]:
    """Postings scoring at or above the search's ``min_score``, respecting its
    filters, newest ``posted_at`` first."""
    saved_search = await session.get(SavedSearch, saved_search_id)
    if saved_search is None:
        raise NotFoundError(f"saved search {saved_search_id} not found")

    filters = SearchFilters.model_validate(saved_search.filters or {})

    conditions = [
        PostingMatch.saved_search_id == saved_search_id,
        PostingMatch.score >= saved_search.min_score,
        Posting.is_active.is_(True),
        # Ownership invariant, enforced at read time too (defense in depth): a
        # match row that predates the owner unwatching a board — or that a prior
        # buggy run wrote out of scope — must not surface. Because the join is
        # against boards *currently* owned/system, deleting a board immediately
        # drops its postings from the feed with no separate cleanup job.
        visible_board_condition(saved_search.user_id),
    ]
    if filters.locations:
        conditions.append(or_(*(Posting.location.ilike(f"%{loc}%") for loc in filters.locations)))
    if filters.departments:
        conditions.append(
            or_(*(Posting.department.ilike(f"%{dep}%") for dep in filters.departments))
        )

    rows = (
        await session.execute(
            select(PostingMatch, Posting, SourceBoard.company_name)
            .join(Posting, PostingMatch.posting_id == Posting.id)
            .join(SourceBoard, Posting.source_board_id == SourceBoard.id)
            .where(*conditions)
            .order_by(Posting.posted_at.desc().nulls_last())
        )
    ).all()

    return [
        PostingMatchRead(
            posting_id=posting.id,
            title=posting.title,
            company_name=company_name,
            location=posting.location,
            department=posting.department,
            url=posting.url,
            posted_at=posting.posted_at,
            score=match.score,
            missing_terms=list(match.missing_terms),
            computed_at=match.computed_at,
        )
        for match, posting, company_name in rows
    ]
