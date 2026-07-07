"""Company career RSS/Atom feed client.

Unlike Greenhouse/Lever there is no ``board_token`` — the identifier *is* the
feed URL. RSS feeds are heterogeneous, so we deliberately extract only what is
reliably present: title, link, and summary. We do **not** try to parse
structured location/department out of free-form feed entries — those stay
``None`` and matching relies on title + summary.

feedparser does blocking network IO and its own tolerant parsing; it is run in
a worker thread so it never blocks the event loop. A broken feed (bozo flag
with no entries, or an HTTP error status) becomes a typed ``FeedUnavailableError``.
"""

import asyncio
from datetime import UTC, datetime
from time import struct_time
from typing import Any

import feedparser

from app.schemas.sources import RawPosting
from app.services.sources.base import USER_AGENT, FeedUnavailableError

_SOURCE = "rss"


class RssClient:
    """Lists entries from a single RSS/Atom career feed URL."""

    source = _SOURCE

    async def list_postings(self, board_token: str) -> list[RawPosting]:
        """``board_token`` is the feed URL for this source."""
        feed_url = board_token
        parsed = await asyncio.to_thread(feedparser.parse, feed_url, agent=USER_AGENT)

        status = parsed.get("status")
        if isinstance(status, int) and status >= 400:
            raise FeedUnavailableError(feed_url, f"HTTP {status}")

        entries = parsed.get("entries") or []
        # A bozo flag with no usable entries means the feed is genuinely broken
        # (malformed XML, an HTML error page, a dead host). Minor well-formedness
        # warnings on a feed that still yielded entries are tolerated.
        if parsed.get("bozo") and not entries:
            detail = str(parsed.get("bozo_exception") or "malformed feed")
            raise FeedUnavailableError(feed_url, detail)

        return [self._map(entry, feed_url) for entry in entries]

    def _map(self, entry: dict[str, Any], feed_url: str) -> RawPosting:
        link = entry.get("link") or ""
        return RawPosting(
            # Prefer the entry's stable guid; fall back to link, then title+feed.
            external_id=entry.get("id") or link or f"{feed_url}#{entry.get('title', '')}",
            title=entry.get("title") or "",
            location=None,  # heterogeneous feeds — do not guess structured fields
            department=None,
            url=link,
            raw_description_html=entry.get("summary") or "",
            posted_at=_parse_dt(entry.get("published_parsed")),
            source=_SOURCE,
        )


def _parse_dt(value: struct_time | None) -> datetime | None:
    """feedparser gives ``published_parsed`` as a UTC ``time.struct_time``."""
    if value is None:
        return None
    try:
        return datetime(*value[:6], tzinfo=UTC)
    except (ValueError, TypeError):
        return None
