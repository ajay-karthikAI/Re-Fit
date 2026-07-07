"""Shared contract and plumbing for external job-source clients.

Each source (Greenhouse, Lever, ...) is its own module implementing the
``SourceClient`` protocol. They will drift and break independently in practice,
so the only things shared here are the parts that *must* behave identically:
the typed error taxonomy, the honest User-Agent, the retry/timeout policy, and
the HTML-to-text cleaner. Everything source-specific (URLs, field mapping)
lives in the per-source module to keep blast radius contained.
"""

import asyncio
import json
import re
from typing import Any, Protocol, runtime_checkable

import httpx
from bs4 import BeautifulSoup

from app.schemas.sources import RawPosting, SourceName

USER_AGENT = "RefitBot/0.1 (personal job-search tool)"
"""Honest identification for these public, no-auth APIs. Be a good citizen."""

REQUEST_TIMEOUT = 10.0
"""Seconds. Applies to connect + read for every request."""

MAX_ATTEMPTS = 3
"""Total tries per request. Retries cover only transient failures (5xx/timeout)."""

_BACKOFF_BASE = 0.5
"""Seconds; delay before retry N is ``_BACKOFF_BASE * 2**N`` (0.5s, 1s)."""


# --- Typed errors -----------------------------------------------------------
# One dead board must never crash a whole ingestion run, and must never fail
# silently either. Callers catch these and degrade the board's health.


class SourceError(Exception):
    """Base for anything that went wrong talking to a source."""


class BoardNotFoundError(SourceError):
    """The board/token does not exist upstream (HTTP 404). This is a real
    not-found — the board was deleted, renamed, or the token is wrong. Never
    retried."""

    def __init__(self, source: SourceName, board_token: str) -> None:
        self.source = source
        self.board_token = board_token
        super().__init__(f"{source} board {board_token!r} not found (404)")


class SourceUnavailableError(SourceError):
    """The source could not be reached or returned an unexpected status after
    retries (timeout, connection error, 5xx, or a non-404 4xx)."""

    def __init__(self, source: SourceName, board_token: str, detail: str) -> None:
        self.source = source
        self.board_token = board_token
        super().__init__(f"{source} board {board_token!r} unavailable: {detail}")


class SourceParseError(SourceError):
    """The response was reachable but not the shape we expected (malformed JSON
    or missing/mistyped fields). A crash here would be an unhandled bug; this
    turns it into a board-health signal instead."""

    def __init__(self, source: SourceName, board_token: str, detail: str) -> None:
        self.source = source
        self.board_token = board_token
        super().__init__(f"{source} board {board_token!r} returned unparseable data: {detail}")


class FeedUnavailableError(SourceError):
    """An RSS/Atom feed could not be fetched or parsed (feedparser bozo flag, a
    4xx/5xx status, or no usable entries). The RSS analogue of the HTTP clients'
    not-found/unavailable errors."""

    def __init__(self, feed_url: str, detail: str) -> None:
        self.source = "rss"
        self.board_token = feed_url
        super().__init__(f"rss feed {feed_url!r} unavailable: {detail}")


# --- Protocol ---------------------------------------------------------------


@runtime_checkable
class SourceClient(Protocol):
    """A pluggable client for one external job source.

    Implementations are swappable and isolated: a caller depends only on this
    protocol so a broken source can be disabled without touching the others.
    """

    source: SourceName

    async def list_postings(self, board_token: str) -> list[RawPosting]:
        """Fetch every current posting for one board/site on this source.

        Raises ``BoardNotFoundError`` for a real 404, ``SourceUnavailableError``
        for transient/unexpected transport failures, and ``SourceParseError``
        for a malformed response. Never raises a bare/unhandled exception for a
        board that simply went bad.
        """
        ...


# --- Shared HTTP fetch ------------------------------------------------------


async def fetch_json(
    url: str,
    *,
    source: SourceName,
    board_token: str,
    client: httpx.AsyncClient | None = None,
) -> Any:
    """GET ``url`` and return decoded JSON, applying the shared source policy.

    Retries only transient failures (timeout, connection error, 5xx) up to
    ``MAX_ATTEMPTS`` with exponential backoff. A 404 is a real not-found and is
    *never* retried. Malformed JSON becomes a typed ``SourceParseError``.

    Pass ``client`` to reuse a connection pool across many boards; otherwise a
    short-lived client is created per call.
    """
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
    try:
        last_detail = "no attempts made"
        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = await client.get(url, headers={"User-Agent": USER_AGENT})
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_detail = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code == 404:
                    raise BoardNotFoundError(source, board_token)
                if resp.status_code >= 500:
                    last_detail = f"HTTP {resp.status_code}"
                elif resp.status_code >= 400:
                    # Non-404 client error: not transient, don't retry.
                    raise SourceUnavailableError(source, board_token, f"HTTP {resp.status_code}")
                else:
                    try:
                        return resp.json()
                    except (json.JSONDecodeError, ValueError) as exc:
                        raise SourceParseError(source, board_token, f"invalid JSON: {exc}") from exc

            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(_BACKOFF_BASE * 2**attempt)

        raise SourceUnavailableError(
            source, board_token, f"{last_detail} after {MAX_ATTEMPTS} attempts"
        )
    finally:
        if owns_client:
            await client.aclose()


# --- HTML -> text -----------------------------------------------------------

_BLOCK_TAGS = ["p", "div", "ul", "ol", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"]


def html_to_text(raw: str) -> str:
    """Strip HTML to clean text, preserving list/paragraph structure as line
    breaks — the same shape Phase 1 gave resume PDFs, not a new pipeline.

    Idempotent-ish on already-plain input (Lever ``descriptionPlain``): with no
    tags to strip it just normalizes whitespace and non-breaking spaces.
    """
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    # Turn structural boundaries into newlines before flattening.
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    text = soup.get_text()
    text = text.replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)  # collapse runs of blank lines to one
    return text.strip()
