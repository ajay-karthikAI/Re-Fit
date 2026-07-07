"""Recurring-jobs + digest tests: the digest "new since last time" window, the
beat schedule registration, staggered/​capped ingestion concurrency, and the
board health surfacing. Real refit_test DB; the sources are stubbed so no
network is touched."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from celery.schedules import crontab
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Digest, Posting, PostingMatch, Profile, SavedSearch, SourceBoard, User
from app.models.source_board import BoardHealth, SourceKind
from app.schemas.postings import IngestResult
from app.services import ingestion
from app.services.digest import build_digest, send_daily_digests
from app.services.postings import content_hash
from app.services.source_boards import list_source_boards
from app.worker import celery_app


async def _user_profile(session: AsyncSession) -> Profile:
    user = User(email=f"u-{datetime.now(UTC).timestamp()}@example.com")
    session.add(user)
    await session.commit()
    profile = Profile(user_id=user.id, data={"contact": {"full_name": "X", "email": "x@y.z"}})
    session.add(profile)
    await session.commit()
    return profile


async def _board(session: AsyncSession, **kw) -> SourceBoard:
    board = SourceBoard(
        source=kw.get("source", SourceKind.greenhouse),
        identifier=kw.get("identifier", "acme"),
        company_name=kw.get("company", "Acme AI"),
        user_id=kw.get("user_id"),  # None -> system/seed board watched for everyone
    )
    for attr in ("health", "consecutive_failures"):
        if attr in kw:
            setattr(board, attr, kw[attr])
    session.add(board)
    await session.commit()
    return board


async def _posting(session: AsyncSession, board: SourceBoard, ext: str) -> Posting:
    posting = Posting(
        source_board_id=board.id,
        external_id=ext,
        title=f"Role {ext}",
        location="Remote",
        department="ML",
        url=f"https://x/{ext}",
        description_text="desc",
        posted_at=datetime.now(UTC),
        content_hash=content_hash(f"Role {ext}", "desc"),
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        is_active=True,
    )
    session.add(posting)
    await session.commit()
    return posting


async def _match(
    session: AsyncSession, search: SavedSearch, posting: Posting, score: float, computed_at
) -> None:
    session.add(
        PostingMatch(
            posting_id=posting.id,
            saved_search_id=search.id,
            score=score,
            missing_terms=[],
            computed_at=computed_at,
            scored_content_hash=posting.content_hash,
            scored_profile_id=search.profile_id,
        )
    )
    await session.commit()


# --- Digest "new since last time" window ------------------------------------


async def test_digest_only_includes_matches_newer_than_last_sent(
    session: AsyncSession,
) -> None:
    profile = await _user_profile(session)
    board = await _board(session)
    search = SavedSearch(user_id=profile.user_id, name="s", profile_id=profile.id, min_score=75.0)
    session.add(search)
    await session.commit()

    t0 = datetime.now(UTC)
    search.last_digest_sent_at = t0
    await session.commit()

    fresh = await _posting(session, board, "fresh")
    old = await _posting(session, board, "old")
    lowscore = await _posting(session, board, "low")
    await _match(session, search, fresh, 90.0, t0 + timedelta(minutes=10))  # new + high
    await _match(session, search, old, 90.0, t0 - timedelta(minutes=10))  # before cutoff
    await _match(session, search, lowscore, 50.0, t0 + timedelta(minutes=10))  # below min

    digest = await build_digest(session, search)

    assert digest.count == 1
    assert [m.posting_id for m in digest.new_matches] == [fresh.id]
    assert len(digest.top_3_preview) == 1


async def test_first_digest_uses_lookback_window(session: AsyncSession) -> None:
    profile = await _user_profile(session)
    board = await _board(session)
    search = SavedSearch(user_id=profile.user_id, name="s", profile_id=profile.id, min_score=75.0)
    session.add(search)
    await session.commit()  # last_digest_sent_at is NULL

    now = datetime.now(UTC)
    recent = await _posting(session, board, "recent")
    stale = await _posting(session, board, "stale")
    await _match(session, search, recent, 90.0, now - timedelta(hours=2))  # within 24h
    await _match(session, search, stale, 90.0, now - timedelta(hours=30))  # older than 24h

    digest = await build_digest(session, search)

    assert [m.posting_id for m in digest.new_matches] == [recent.id]


async def test_send_daily_digests_persists_and_advances_watermark(
    session: AsyncSession,
) -> None:
    profile = await _user_profile(session)
    board = await _board(session)
    search = SavedSearch(user_id=profile.user_id, name="s", profile_id=profile.id, min_score=75.0)
    session.add(search)
    await session.commit()

    posting = await _posting(session, board, "p1")
    await _match(session, search, posting, 90.0, datetime.now(UTC))

    generated = await send_daily_digests(session)
    assert generated == 1

    digests = (await session.execute(__import__("sqlalchemy").select(Digest))).scalars().all()
    assert len(digests) == 1
    assert digests[0].posting_ids == [str(posting.id)]
    assert digests[0].new_match_count == 1
    await session.refresh(search)
    assert search.last_digest_sent_at is not None

    # Nothing new since the watermark -> no second digest.
    again = await send_daily_digests(session)
    assert again == 0


# --- Digest respects the same ownership scoping -----------------------------


async def test_digest_scoped_to_owner_plus_system_boards(session: AsyncSession) -> None:
    """The two-user fixture again: user A's digest includes matches on their own
    board and the system board, but never a posting on user B's board — even if a
    stale, out-of-scope match row exists (reuses the /matches ownership join)."""
    profile_a = await _user_profile(session)
    profile_b = await _user_profile(session)

    board_a = await _board(session, identifier="a", company="A Co", user_id=profile_a.user_id)
    board_b = await _board(session, identifier="b", company="B Co", user_id=profile_b.user_id)
    system_board = await _board(session, identifier="s", company="Sys Co", user_id=None)

    posting_a = await _posting(session, board_a, "a")
    posting_b = await _posting(session, board_b, "b")
    posting_sys = await _posting(session, system_board, "s")

    search_a = SavedSearch(
        user_id=profile_a.user_id, name="s", profile_id=profile_a.id, min_score=75.0
    )
    session.add(search_a)
    await session.commit()

    now = datetime.now(UTC)
    await _match(session, search_a, posting_a, 90.0, now)
    await _match(session, search_a, posting_sys, 90.0, now)
    await _match(session, search_a, posting_b, 95.0, now)  # stale out-of-scope row

    digest = await build_digest(session, search_a)

    ids = {m.posting_id for m in digest.new_matches}
    assert ids == {posting_a.id, posting_sys.id}
    assert posting_b.id not in ids


# --- Beat schedule registration ---------------------------------------------


def test_beat_schedule_registered_correctly() -> None:
    schedule = celery_app.conf.beat_schedule
    assert set(schedule) == {
        "ingest-all-boards",
        "rescore-active-searches",
        "freshness-cleanup",
        "send-daily-digest",
    }
    assert schedule["ingest-all-boards"]["task"] == "app.worker.ingest_all_boards_task"
    # Rescore is offset one hour after ingestion.
    ingest_hours = schedule["ingest-all-boards"]["schedule"]
    rescore_hours = schedule["rescore-active-searches"]["schedule"]
    assert isinstance(ingest_hours, crontab) and isinstance(rescore_hours, crontab)
    assert ingest_hours.hour == {0, 6, 12, 18}
    assert rescore_hours.hour == {1, 7, 13, 19}
    assert schedule["freshness-cleanup"]["schedule"].hour == {3}


# --- Staggered ingestion respects the concurrency cap -----------------------


async def test_ingestion_respects_concurrency_cap(
    session: AsyncSession, engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Five active boards, cap of 2: never more than 2 fetches in flight.
    for i in range(5):
        await _board(session, identifier=f"b{i}", company=f"C{i}")

    state = {"cur": 0, "max": 0}

    async def fake_fetch(sess, board):
        state["cur"] += 1
        state["max"] = max(state["max"], state["cur"])
        await asyncio.sleep(0.05)
        state["cur"] -= 1
        return []

    async def fake_upsert(sess, board, raws):
        return IngestResult()

    monkeypatch.setattr(ingestion, "fetch_board", fake_fetch)
    monkeypatch.setattr(ingestion, "upsert_postings", fake_upsert)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    await ingestion.ingest_all_boards(factory, concurrency=2, stagger_seconds=0.0)

    assert state["max"] == 2  # reached the cap but never exceeded it


# --- Operational visibility -------------------------------------------------


async def test_ailing_boards_surface_first_with_needs_attention(
    session: AsyncSession,
) -> None:
    healthy = await _board(session, identifier="ok", company="Healthy Co")
    ailing = await _board(
        session,
        identifier="bad",
        company="Ailing Co",
        health=BoardHealth.degraded,
        consecutive_failures=4,
    )

    boards = await list_source_boards(session)

    assert boards[0].id == ailing.id  # ailing first
    assert boards[0].needs_attention is True
    assert next(b for b in boards if b.id == healthy.id).needs_attention is False
