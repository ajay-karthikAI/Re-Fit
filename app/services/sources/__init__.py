"""External job-source clients (Greenhouse, Lever, RSS).

Each source is an isolated, swappable module implementing the ``SourceClient``
protocol from ``base``. ``registry.fetch_board`` ties them together behind one
board-aware, health-tracking entry point. See ``CLAUDE.md`` (Phase 4 scope
lock) for the capped source allow-list.
"""

from app.services.sources.base import (
    BoardNotFoundError,
    FeedUnavailableError,
    SourceClient,
    SourceError,
    SourceParseError,
    SourceUnavailableError,
    html_to_text,
)
from app.services.sources.greenhouse import GreenhouseClient
from app.services.sources.lever import LeverClient
from app.services.sources.registry import client_for, fetch_board
from app.services.sources.rss import RssClient

__all__ = [
    "SourceClient",
    "SourceError",
    "BoardNotFoundError",
    "SourceUnavailableError",
    "SourceParseError",
    "FeedUnavailableError",
    "GreenhouseClient",
    "LeverClient",
    "RssClient",
    "client_for",
    "fetch_board",
    "html_to_text",
]
