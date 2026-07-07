"""The Job Feed's one-click bridge: turning a matched posting into a job target.

Covers the source_ats-from-board-type rule (so Phase 3's assisted-apply screen
works on arrival) and the per-(user, source_url) idempotency that keeps a second
Generate-kit click landing on the same kit instead of spawning duplicates.
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Posting, SourceBoard, User
from app.models.source_board import SourceKind
from app.services import job_targets
from app.services.errors import NotFoundError
from app.services.postings import content_hash


async def _user(session: AsyncSession) -> User:
    user = User(email=f"u-{datetime.now(UTC).timestamp()}@example.com")
    session.add(user)
    await session.commit()
    return user


async def _posting(
    session: AsyncSession, source: SourceKind, url: str, *, company: str = "Acme AI"
) -> tuple[SourceBoard, Posting]:
    board = SourceBoard(
        source=source, identifier="acme", company_name=company, user_id=None
    )
    session.add(board)
    await session.commit()
    posting = Posting(
        source_board_id=board.id,
        external_id="ext-1",
        title="Staff ML Engineer",
        location="Remote",
        department="ML",
        url=url,
        description_text="Build production ML systems in Python.",
        posted_at=datetime.now(UTC),
        content_hash=content_hash("Staff ML Engineer", "Build production ML systems in Python."),
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    session.add(posting)
    await session.commit()
    return board, posting


@pytest.mark.asyncio
async def test_from_posting_populates_fields_and_ats_from_board(session: AsyncSession) -> None:
    user = await _user(session)
    board, posting = await _posting(
        session, SourceKind.greenhouse, "https://boards.greenhouse.io/acme/jobs/1", company="Acme AI"
    )

    target = await job_targets.create_job_target_from_posting(session, posting.id, user.id)

    assert target.user_id == user.id
    assert target.company == "Acme AI"  # from the source board, not the posting
    assert target.title == posting.title
    assert target.source_url == posting.url
    assert target.raw_description == posting.description_text
    assert target.source_ats == "greenhouse"  # from the board type


@pytest.mark.asyncio
async def test_from_posting_lever_board_sets_lever_ats(session: AsyncSession) -> None:
    user = await _user(session)
    _board, posting = await _posting(session, SourceKind.lever, "https://jobs.lever.co/acme/1")

    target = await job_targets.create_job_target_from_posting(session, posting.id, user.id)

    assert target.source_ats == "lever"


@pytest.mark.asyncio
async def test_from_posting_rss_falls_back_to_url_sniff(session: AsyncSession) -> None:
    user = await _user(session)
    # RSS feed that syndicates a Greenhouse apply link.
    _board, posting = await _posting(
        session, SourceKind.rss, "https://boards.greenhouse.io/acme/jobs/9"
    )

    target = await job_targets.create_job_target_from_posting(session, posting.id, user.id)

    assert target.source_ats == "greenhouse"


@pytest.mark.asyncio
async def test_from_posting_is_idempotent_per_user_and_url(session: AsyncSession) -> None:
    user = await _user(session)
    _board, posting = await _posting(
        session, SourceKind.greenhouse, "https://boards.greenhouse.io/acme/jobs/2"
    )

    first = await job_targets.create_job_target_from_posting(session, posting.id, user.id)
    second = await job_targets.create_job_target_from_posting(session, posting.id, user.id)

    assert first.id == second.id


@pytest.mark.asyncio
async def test_from_posting_missing_posting_raises(session: AsyncSession) -> None:
    user = await _user(session)
    import uuid

    with pytest.raises(NotFoundError):
        await job_targets.create_job_target_from_posting(session, uuid.uuid4(), user.id)


@pytest.mark.asyncio
async def test_from_posting_endpoint_returns_201(client: AsyncClient, session: AsyncSession) -> None:
    user = await _user(session)
    _board, posting = await _posting(
        session, SourceKind.greenhouse, "https://boards.greenhouse.io/acme/jobs/3"
    )

    response = await client.post(
        f"/postings/{posting.id}/job-target", json={"user_id": str(user.id)}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source_ats"] == "greenhouse"
    assert body["company"] == "Acme AI"
    assert body["source_url"] == posting.url
