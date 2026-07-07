"""Digest generation — the payoff of the whole phase.

A digest is the set of matches that are *new to the user* since the last digest
for a saved search: postings clearing its ``min_score`` whose match was computed
after ``last_digest_sent_at`` (or within the lookback window on the very first
digest). Tracking ``last_digest_sent_at`` is what stops the user from being
shown the same jobs every day.

Generation is deliberately split from **delivery**: ``build_digest`` computes the
content and ``send_daily_digests`` persists a ``Digest`` row, but nothing here
emails or pushes anything. Delivery channels (email, push, in-app only) are a
separate concern that can be swapped without touching this logic (see CLAUDE.md).
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Digest as DigestModel
from app.models import Posting, PostingMatch, SavedSearch, SourceBoard
from app.schemas.saved_search import Digest, PostingMatchRead
from app.services.errors import NotFoundError
from app.services.matching import visible_board_condition

logger = logging.getLogger(__name__)

_PREVIEW_SIZE = 3


async def build_digest(session: AsyncSession, saved_search: SavedSearch) -> Digest:
    """Build (not persist) the digest of matches new to the user for one search.

    "New" = match score >= the search's ``min_score`` and ``computed_at`` after
    the last digest, or within the configured lookback if no digest has ever run.
    Ordered newest match first.
    """
    settings = get_settings()
    if saved_search.last_digest_sent_at is not None:
        cutoff = saved_search.last_digest_sent_at
    else:
        cutoff = datetime.now(UTC) - timedelta(hours=settings.digest_lookback_hours)

    rows = (
        await session.execute(
            select(PostingMatch, Posting, SourceBoard.company_name)
            .join(Posting, PostingMatch.posting_id == Posting.id)
            .join(SourceBoard, Posting.source_board_id == SourceBoard.id)
            .where(
                PostingMatch.saved_search_id == saved_search.id,
                PostingMatch.score >= saved_search.min_score,
                PostingMatch.computed_at > cutoff,
                Posting.is_active.is_(True),
                # Same ownership invariant as the /matches query (this join is why
                # the digest inherits scoping for free): only the owner's own
                # boards plus system/seed boards.
                visible_board_condition(saved_search.user_id),
            )
            .order_by(PostingMatch.computed_at.desc(), PostingMatch.score.desc())
        )
    ).all()

    new_matches = [
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
    return Digest(
        saved_search_id=saved_search.id,
        count=len(new_matches),
        new_matches=new_matches,
        top_3_preview=new_matches[:_PREVIEW_SIZE],
    )


async def send_daily_digests(session: AsyncSession) -> int:
    """For every active saved search with new matches, persist a Digest row and
    advance ``last_digest_sent_at``. Returns the number of digests generated.

    "Send" is a misnomer kept for the task name — this only *generates*. Delivery
    is a separate concern layered on top of the persisted rows.
    """
    now = datetime.now(UTC)
    searches = (
        (await session.execute(select(SavedSearch).where(SavedSearch.is_active.is_(True))))
        .scalars()
        .all()
    )

    generated = 0
    for saved_search in searches:
        digest = await build_digest(session, saved_search)
        if digest.count == 0:
            continue
        session.add(
            DigestModel(
                saved_search_id=saved_search.id,
                new_match_count=digest.count,
                posting_ids=[str(m.posting_id) for m in digest.new_matches],
            )
        )
        saved_search.last_digest_sent_at = now
        generated += 1

    await session.commit()
    logger.info("generated %d digest(s)", generated)
    return generated


async def list_digests(session: AsyncSession, saved_search_id) -> list[DigestModel]:
    saved_search = await session.get(SavedSearch, saved_search_id)
    if saved_search is None:
        raise NotFoundError(f"saved search {saved_search_id} not found")
    result = await session.execute(
        select(DigestModel)
        .where(DigestModel.saved_search_id == saved_search_id)
        .order_by(DigestModel.created_at.desc())
    )
    return list(result.scalars().all())
