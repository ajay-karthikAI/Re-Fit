"""Ties the three source clients together behind one board-aware entry point.

``fetch_board`` is the only function ingestion needs to call. It dispatches to
the right client by ``board.source``, and — crucially — owns the board's health
lifecycle: a run either resets the failure streak or advances it, degrading and
eventually killing a board that keeps failing so we stop hammering it. Expected
source failures never propagate out of here; the caller inspects ``board.health``
for alerting instead of catching exceptions.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.source_board import BoardHealth, SourceBoard, SourceKind
from app.schemas.sources import RawPosting
from app.services.sources.base import SourceClient, SourceError
from app.services.sources.greenhouse import GreenhouseClient
from app.services.sources.lever import LeverClient
from app.services.sources.rss import RssClient


def client_for(source: SourceKind) -> SourceClient:
    """Return the isolated client that handles ``source``."""
    match source:
        case SourceKind.greenhouse:
            return GreenhouseClient()
        case SourceKind.lever:
            return LeverClient()
        case SourceKind.rss:
            return RssClient()
    raise ValueError(f"no client registered for source {source!r}")


def _health_for(consecutive_failures: int) -> BoardHealth:
    settings = get_settings()
    if consecutive_failures >= settings.board_dead_after:
        return BoardHealth.dead
    if consecutive_failures >= settings.board_degraded_after:
        return BoardHealth.degraded
    return BoardHealth.healthy


async def fetch_board(session: AsyncSession, board: SourceBoard) -> list[RawPosting]:
    """Fetch one board's postings and record the outcome on the board.

    On success: reset ``consecutive_failures`` to 0, stamp ``last_success_at``,
    and mark the board ``healthy``. On an expected source failure: increment
    ``consecutive_failures``, recompute ``health`` against the configured
    thresholds, and return ``[]`` — never raise. ``last_checked_at`` is stamped
    either way. Unexpected (non-``SourceError``) exceptions are left to
    propagate; those are bugs, not board health signals.
    """
    now = datetime.now(UTC)
    client = client_for(board.source)
    try:
        postings = await client.list_postings(board.identifier)
    except SourceError:
        board.consecutive_failures += 1
        board.health = _health_for(board.consecutive_failures)
        board.last_checked_at = now
        await session.commit()
        return []

    board.consecutive_failures = 0
    board.health = BoardHealth.healthy
    board.last_checked_at = now
    board.last_success_at = now
    await session.commit()
    return postings
