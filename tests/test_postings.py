"""Storage + dedup layer: upsert idempotency, change detection, soft expiry,
cross-board fuzzy linking, and the freshness sweep. Real refit_test DB per
CLAUDE.md — never mocked."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.posting import Posting
from app.models.source_board import SourceBoard, SourceKind
from app.services.postings import (
    deactivate_stale_postings,
    upsert_postings,
)
from app.schemas.sources import RawPosting


def _raw(
    external_id: str,
    *,
    title: str = "Machine Learning Engineer",
    desc: str = "Build and ship models.",
    source: str = "greenhouse",
) -> RawPosting:
    return RawPosting(
        external_id=external_id,
        title=title,
        location="Remote",
        department="ML",
        url=f"https://example.com/jobs/{external_id}",
        raw_description_html=desc,
        posted_at=None,
        source=source,  # type: ignore[arg-type]
    )


async def _board(
    session: AsyncSession,
    *,
    source: SourceKind = SourceKind.greenhouse,
    company: str = "Acme AI",
    identifier: str = "acme",
) -> SourceBoard:
    board = SourceBoard(source=source, identifier=identifier, company_name=company)
    session.add(board)
    await session.commit()
    return board


async def _count(session: AsyncSession, board_id=None) -> int:
    stmt = select(func.count()).select_from(Posting)
    if board_id is not None:
        stmt = stmt.where(Posting.source_board_id == board_id)
    return (await session.execute(stmt)).scalar_one()


# --- Idempotency ------------------------------------------------------------


async def test_upsert_twice_identical_is_all_unchanged(session: AsyncSession) -> None:
    board = await _board(session)
    postings = [_raw("1"), _raw("2"), _raw("3")]

    first = await upsert_postings(session, board, postings)
    assert (first.created, first.updated, first.unchanged, first.deactivated) == (3, 0, 0, 0)

    second = await upsert_postings(session, board, postings)
    assert (second.created, second.updated, second.unchanged, second.deactivated) == (0, 0, 3, 0)
    assert await _count(session, board.id) == 3  # no new rows on re-fetch


# --- Change detection -------------------------------------------------------


async def test_content_change_is_updated_not_created(session: AsyncSession) -> None:
    board = await _board(session)
    await upsert_postings(session, board, [_raw("1", desc="Original description.")])

    result = await upsert_postings(
        session, board, [_raw("1", desc="Revised, expanded description.")]
    )

    assert (result.created, result.updated, result.unchanged) == (0, 1, 0)
    assert await _count(session, board.id) == 1  # same row, updated in place
    row = (await session.execute(select(Posting).where(Posting.external_id == "1"))).scalar_one()
    assert row.description_text == "Revised, expanded description."


# --- Soft expiry ------------------------------------------------------------


async def test_missing_from_refetch_is_deactivated(session: AsyncSession) -> None:
    board = await _board(session)
    await upsert_postings(session, board, [_raw("1"), _raw("2")])

    result = await upsert_postings(session, board, [_raw("1")])  # "2" dropped out

    assert result.deactivated == 1
    assert await _count(session, board.id) == 2  # soft expiry: no delete
    gone = (await session.execute(select(Posting).where(Posting.external_id == "2"))).scalar_one()
    assert gone.is_active is False
    assert gone.deactivated_at is not None


async def test_reappearing_posting_is_reactivated_and_counts_as_updated(
    session: AsyncSession,
) -> None:
    board = await _board(session)
    await upsert_postings(session, board, [_raw("1"), _raw("2")])
    await upsert_postings(session, board, [_raw("1")])  # deactivates "2"

    result = await upsert_postings(session, board, [_raw("1"), _raw("2")])  # "2" returns

    assert result.updated == 1  # reactivation re-triggers scoring
    back = (await session.execute(select(Posting).where(Posting.external_id == "2"))).scalar_one()
    assert back.is_active is True
    assert back.deactivated_at is None


# --- Cross-board fuzzy dedup ------------------------------------------------


async def test_cross_board_duplicate_is_linked_but_both_rows_survive(
    session: AsyncSession,
) -> None:
    gh = await _board(session, source=SourceKind.greenhouse, company="Acme AI", identifier="acme")
    rss = await _board(
        session, source=SourceKind.rss, company="Acme AI", identifier="https://acme/feed"
    )
    title = "Senior Machine Learning Engineer, Ranking"

    await upsert_postings(session, gh, [_raw("gh-1", title=title)])
    await upsert_postings(session, rss, [_raw("rss-1", title=title)])

    gh_row = (
        await session.execute(select(Posting).where(Posting.external_id == "gh-1"))
    ).scalar_one()
    rss_row = (
        await session.execute(select(Posting).where(Posting.external_id == "rss-1"))
    ).scalar_one()

    # Both rows survive; the newer (RSS) one is linked to the older canonical.
    assert await _count(session) == 2
    assert gh_row.canonical_posting_id is None  # first seen stays canonical
    assert rss_row.canonical_posting_id == gh_row.id


async def test_distinct_roles_are_not_merged(session: AsyncSession) -> None:
    gh = await _board(session, source=SourceKind.greenhouse, company="Acme AI", identifier="acme")
    rss = await _board(
        session, source=SourceKind.rss, company="Acme AI", identifier="https://acme/feed"
    )
    await upsert_postings(session, gh, [_raw("gh-1", title="Machine Learning Engineer")])
    await upsert_postings(session, rss, [_raw("rss-1", title="Senior Accountant, Payroll")])

    rss_row = (
        await session.execute(select(Posting).where(Posting.external_id == "rss-1"))
    ).scalar_one()
    assert rss_row.canonical_posting_id is None  # under-merge bias: left unlinked


# --- Freshness sweep --------------------------------------------------------


async def test_freshness_cleanup_deactivates_old_actives(session: AsyncSession) -> None:
    board = await _board(session)
    await upsert_postings(session, board, [_raw("old"), _raw("fresh")])

    # Age "old" past the 45-day window without going through a fetch.
    old = (await session.execute(select(Posting).where(Posting.external_id == "old"))).scalar_one()
    old.last_seen_at = datetime.now(UTC) - timedelta(days=60)
    await session.commit()

    deactivated = await deactivate_stale_postings(session)

    assert deactivated == 1
    await session.refresh(old)
    assert old.is_active is False and old.deactivated_at is not None
    fresh = (
        await session.execute(select(Posting).where(Posting.external_id == "fresh"))
    ).scalar_one()
    assert fresh.is_active is True  # within the window, untouched
