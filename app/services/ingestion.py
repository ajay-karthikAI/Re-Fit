"""Recurring ingestion orchestration: fetch every active board, upsert, rescore.

These are the bodies behind the Celery beat tasks in ``app/worker.py``. They own
the "be a good API citizen" policy: boards are fetched with a concurrency cap and
a per-board launch stagger, never all at once. Each board fetch runs on its own
DB session so the capped fan-out is genuinely concurrent without sharing a
session.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db import get_session_factory
from app.models import SavedSearch, SourceBoard
from app.models.source_board import BoardHealth
from app.services.matching import refresh_matches_for_search
from app.services.postings import deactivate_stale_postings, upsert_postings
from app.services.sources.registry import fetch_board

logger = logging.getLogger(__name__)


async def ingest_all_boards(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    *,
    concurrency: int | None = None,
    stagger_seconds: float | None = None,
) -> dict[str, int]:
    """Fetch and upsert every active source board, capped and staggered.

    A semaphore bounds how many boards are in flight at once; a delay between
    launches spreads the initial burst. Returns rollup counts across boards.
    """
    settings = get_settings()
    factory = session_factory or get_session_factory()
    cap = concurrency if concurrency is not None else settings.ingest_concurrency
    delay = stagger_seconds if stagger_seconds is not None else settings.ingest_stagger_seconds

    async with factory() as session:
        # Skip boards already degraded to "dead" — the health system exists so we
        # stop hammering them. Healthy and degraded boards are still fetched
        # (degraded ones need a chance to recover).
        boards = (
            (
                await session.execute(
                    select(SourceBoard).where(SourceBoard.health != BoardHealth.dead)
                )
            )
            .scalars()
            .all()
        )

    semaphore = asyncio.Semaphore(max(1, cap))
    totals = {"boards": 0, "created": 0, "updated": 0, "unchanged": 0, "deactivated": 0}

    async def _ingest_one(board: SourceBoard) -> None:
        async with semaphore:
            async with factory() as session:
                board = await session.get(SourceBoard, board.id)
                if board is None:
                    return
                raws = await fetch_board(session, board)
                result = await upsert_postings(session, board, raws)
            totals["boards"] += 1
            totals["created"] += result.created
            totals["updated"] += result.updated
            totals["unchanged"] += result.unchanged
            totals["deactivated"] += result.deactivated

    tasks: list[asyncio.Task] = []
    for index, board in enumerate(boards):
        if index and delay:
            await asyncio.sleep(delay)  # stagger launches; the cap bounds overlap
        tasks.append(asyncio.create_task(_ingest_one(board)))
    if tasks:
        await asyncio.gather(*tasks)

    logger.info("ingest_all_boards: %s", totals)
    return totals


async def rescore_active_searches(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, int]:
    """Recompute matches for every active saved search. Reuses Prompt 4's skip
    logic, so only new/changed postings actually cost an LLM extraction."""
    factory = session_factory or get_session_factory()
    totals = {"searches": 0, "computed": 0, "skipped": 0}

    async with factory() as session:
        searches = (
            (await session.execute(select(SavedSearch).where(SavedSearch.is_active.is_(True))))
            .scalars()
            .all()
        )
        for saved_search in searches:
            stats = await refresh_matches_for_search(session, saved_search)
            totals["searches"] += 1
            totals["computed"] += stats.computed
            totals["skipped"] += stats.skipped

    logger.info("rescore_active_searches: %s", totals)
    return totals


async def run_freshness_cleanup(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> int:
    """Deactivate postings past the freshness window (e.g. orphaned by dead boards)."""
    factory = session_factory or get_session_factory()
    async with factory() as session:
        count = await deactivate_stale_postings(session)
    logger.info("freshness cleanup deactivated %d posting(s)", count)
    return count
