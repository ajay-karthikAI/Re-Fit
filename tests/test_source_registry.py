"""Registry dispatch, board-health transitions, and RSS bozo handling.

Health-transition tests use the real refit_test DB (per CLAUDE.md — never mock
the database); the source *clients* are stubbed so no network is touched. RSS
tests stub feedparser.parse.
"""

import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source_board import BoardHealth, SourceBoard, SourceKind
from app.services.sources import registry
from app.services.sources.base import BoardNotFoundError, FeedUnavailableError, SourceClient
from app.services.sources.greenhouse import GreenhouseClient
from app.services.sources.lever import LeverClient
from app.services.sources.rss import RssClient


# --- Stub clients -----------------------------------------------------------


class _OkClient:
    source = "greenhouse"

    def __init__(self, postings: list | None = None) -> None:
        self._postings = postings or []
        self.calls: list[str] = []

    async def list_postings(self, board_token: str) -> list:
        self.calls.append(board_token)
        return self._postings


class _FailClient:
    source = "greenhouse"

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def list_postings(self, board_token: str) -> list:
        raise self._exc


# --- Dispatch ---------------------------------------------------------------


def test_client_for_maps_each_source_to_its_client() -> None:
    assert isinstance(registry.client_for(SourceKind.greenhouse), GreenhouseClient)
    assert isinstance(registry.client_for(SourceKind.lever), LeverClient)
    assert isinstance(registry.client_for(SourceKind.rss), RssClient)


def test_registry_clients_satisfy_the_protocol() -> None:
    assert isinstance(registry.client_for(SourceKind.greenhouse), SourceClient)
    assert isinstance(registry.client_for(SourceKind.rss), SourceClient)


async def test_fetch_board_dispatches_to_client_with_board_identifier(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    ok = _OkClient(postings=["one", "two"])
    monkeypatch.setattr(registry, "client_for", lambda source: ok)
    board = SourceBoard(source=SourceKind.lever, identifier="mistral", company_name="Mistral")
    session.add(board)
    await session.commit()

    postings = await registry.fetch_board(session, board)

    assert postings == ["one", "two"]
    assert ok.calls == ["mistral"]  # dispatched using the board's identifier


# --- Health transitions -----------------------------------------------------


async def _new_board(session: AsyncSession) -> SourceBoard:
    board = SourceBoard(source=SourceKind.greenhouse, identifier="pathai", company_name="PathAI")
    session.add(board)
    await session.commit()
    return board


async def test_health_degrades_at_three_then_dies_at_ten(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        registry, "client_for", lambda source: _FailClient(BoardNotFoundError("greenhouse", "x"))
    )
    board = await _new_board(session)

    # Failures 1 and 2: still healthy, but the streak and last_checked advance.
    for expected in (1, 2):
        result = await registry.fetch_board(session, board)
        assert result == []  # expected failure never raises
        assert board.consecutive_failures == expected
        assert board.health == BoardHealth.healthy
        assert board.last_checked_at is not None
        assert board.last_success_at is None

    # Failure 3 crosses the degraded threshold.
    await registry.fetch_board(session, board)
    assert board.consecutive_failures == 3
    assert board.health == BoardHealth.degraded

    # Keep failing up to 10 -> dead.
    while board.consecutive_failures < 10:
        await registry.fetch_board(session, board)
    assert board.consecutive_failures == 10
    assert board.health == BoardHealth.dead


async def test_success_resets_failure_streak_and_health(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    board = await _new_board(session)
    board.consecutive_failures = 5
    board.health = BoardHealth.degraded
    await session.commit()

    monkeypatch.setattr(registry, "client_for", lambda source: _OkClient(postings=["job"]))
    postings = await registry.fetch_board(session, board)

    assert postings == ["job"]
    assert board.consecutive_failures == 0
    assert board.health == BoardHealth.healthy
    assert board.last_success_at is not None
    assert board.last_checked_at is not None


async def test_unexpected_error_propagates(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A non-SourceError is a bug, not a board-health signal: it must NOT be
    # swallowed into an empty list.
    monkeypatch.setattr(registry, "client_for", lambda source: _FailClient(RuntimeError("boom")))
    board = await _new_board(session)

    with pytest.raises(RuntimeError):
        await registry.fetch_board(session, board)


# --- RSS client -------------------------------------------------------------


def _fake_feed(**overrides: object) -> dict:
    feed = {
        "bozo": 0,
        "status": 200,
        "entries": [
            {
                "id": "guid-123",
                "title": "Senior ML Engineer",
                "link": "https://careers.example.com/jobs/123",
                "summary": "<p>Build models.</p><ul><li>Python</li><li>PyTorch</li></ul>",
                "published_parsed": time.struct_time((2026, 7, 1, 12, 0, 0, 0, 0, 0)),
            }
        ],
    }
    feed.update(overrides)
    return feed


async def test_rss_maps_entries_and_leaves_structured_fields_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.sources.rss.feedparser.parse", lambda url, agent: _fake_feed()
    )

    postings = await RssClient().list_postings("https://careers.example.com/feed.xml")

    assert len(postings) == 1
    p = postings[0]
    assert p.source == "rss"
    assert p.external_id == "guid-123"
    assert p.title == "Senior ML Engineer"
    assert p.url == "https://careers.example.com/jobs/123"
    assert p.location is None and p.department is None  # heterogeneous — never guessed
    assert p.posted_at is not None and (p.posted_at.year, p.posted_at.month) == (2026, 7)
    # summary HTML is cleaned the same way as the other sources.
    text = p.description_text
    assert "<" not in text
    assert "Python" in text.splitlines()


async def test_rss_bozo_with_no_entries_raises_feed_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = _fake_feed(bozo=1, entries=[], bozo_exception=Exception("mismatched tag"))
    monkeypatch.setattr("app.services.sources.rss.feedparser.parse", lambda url, agent: broken)

    with pytest.raises(FeedUnavailableError):
        await RssClient().list_postings("https://careers.example.com/broken.xml")


async def test_rss_bozo_with_entries_is_tolerated(monkeypatch: pytest.MonkeyPatch) -> None:
    # A well-formedness warning that still yielded entries should not kill the feed.
    lenient = _fake_feed(bozo=1, bozo_exception=Exception("undefined entity"))
    monkeypatch.setattr("app.services.sources.rss.feedparser.parse", lambda url, agent: lenient)

    postings = await RssClient().list_postings("https://careers.example.com/warn.xml")
    assert len(postings) == 1


async def test_rss_http_error_status_raises_feed_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gone = _fake_feed(status=404, entries=[])
    monkeypatch.setattr("app.services.sources.rss.feedparser.parse", lambda url, agent: gone)

    with pytest.raises(FeedUnavailableError):
        await RssClient().list_postings("https://careers.example.com/404.xml")
