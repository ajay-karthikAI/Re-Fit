"""Greenhouse Job Board API client.

Public, no-auth per-board listing:
``GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true``

The ``content`` field comes back HTML-*entity-encoded* (``&lt;p&gt;``), so it
is unescaped once into real HTML before being handed off as ``raw_description_html``.
"""

from datetime import datetime
from html import unescape
from typing import Any

import httpx

from app.schemas.sources import RawPosting
from app.services.sources.base import SourceParseError, fetch_json

_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"
_SOURCE = "greenhouse"


class GreenhouseClient:
    """Lists postings for a single Greenhouse board token (e.g. ``pathai``)."""

    source = _SOURCE

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def list_postings(self, board_token: str) -> list[RawPosting]:
        url = f"{_BASE_URL}/{board_token}/jobs?content=true"
        data = await fetch_json(url, source=_SOURCE, board_token=board_token, client=self._client)
        try:
            jobs = data["jobs"]
            return [self._map(job, board_token) for job in jobs]
        except (KeyError, TypeError, AttributeError) as exc:
            raise SourceParseError(_SOURCE, board_token, f"unexpected shape: {exc}") from exc

    def _map(self, job: dict[str, Any], board_token: str) -> RawPosting:
        departments = job.get("departments") or []
        department = departments[0].get("name") if departments else None
        location = (job.get("location") or {}).get("name")
        return RawPosting(
            external_id=str(job["id"]),
            title=job["title"],
            location=location,
            department=department,
            url=job["absolute_url"],
            raw_description_html=unescape(job.get("content") or ""),
            posted_at=_parse_dt(job.get("updated_at")),
            source=_SOURCE,
        )


def _parse_dt(value: str | None) -> datetime | None:
    """Greenhouse timestamps are ISO 8601 with a timezone offset."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
