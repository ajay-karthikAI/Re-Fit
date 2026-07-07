"""Lever Postings API client.

Public, no-auth per-site listing:
``GET https://api.lever.co/v0/postings/{site}?mode=json``

Lever returns a bare JSON array of postings. ``createdAt`` is epoch
milliseconds. ``descriptionPlain`` is preferred over ``description`` (already
plain text, list structure preserved as line breaks).
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from app.schemas.sources import RawPosting
from app.services.sources.base import SourceParseError, fetch_json

_BASE_URL = "https://api.lever.co/v0/postings"
_SOURCE = "lever"


class LeverClient:
    """Lists postings for a single Lever site (e.g. ``mistral``)."""

    source = _SOURCE

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def list_postings(self, board_token: str) -> list[RawPosting]:
        url = f"{_BASE_URL}/{board_token}?mode=json"
        data = await fetch_json(url, source=_SOURCE, board_token=board_token, client=self._client)
        if not isinstance(data, list):
            raise SourceParseError(
                _SOURCE, board_token, f"expected a JSON array, got {type(data).__name__}"
            )
        try:
            return [self._map(posting) for posting in data]
        except (KeyError, TypeError, AttributeError) as exc:
            raise SourceParseError(_SOURCE, board_token, f"unexpected shape: {exc}") from exc

    def _map(self, posting: dict[str, Any]) -> RawPosting:
        categories = posting.get("categories") or {}
        description = posting.get("descriptionPlain") or posting.get("description") or ""
        return RawPosting(
            external_id=str(posting["id"]),
            title=posting["text"],
            location=categories.get("location"),
            department=categories.get("team"),
            url=posting["hostedUrl"],
            raw_description_html=description,
            posted_at=_parse_dt(posting.get("createdAt")),
            source=_SOURCE,
        )


def _parse_dt(value: int | None) -> datetime | None:
    """Lever ``createdAt`` is epoch milliseconds."""
    if not value:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    except (ValueError, OSError, OverflowError):
        return None
