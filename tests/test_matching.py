"""Matching layer: reuse Phase 1 scoring on postings, cache to avoid re-running
the LLM extraction, and filter the matches query. Real refit_test DB; the one
LLM path (jd.extract_requirements) is monkeypatched with a call counter so no
network/paid API is touched."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Posting, PostingMatch, Profile, SavedSearch, SourceBoard, User
from app.models.source_board import SourceKind
from app.schemas.jd import JobRequirements, RequirementItem
from app.schemas.llm import LLMUsage
from app.schemas.resume import StructuredResume
from app.services import matching
from app.services.matching import (
    list_matches,
    refresh_matches_for_search,
    score_posting_for_search,
)
from app.services.postings import content_hash


def _resume() -> StructuredResume:
    return StructuredResume(
        contact={"full_name": "Ada Example", "email": "ada@example.com"},
        summary="Machine learning engineer.",
        experience=[
            {
                "company": "Acme",
                "title": "Senior ML Engineer",
                "start_date": "2021-01",
                "end_date": None,
                "bullets": [
                    "Built recommendation models in Python with PyTorch.",
                    "Shipped ranking services serving 10M requests/day.",
                ],
                "technologies": ["Python", "PyTorch"],
            }
        ],
        education=[],
        skills=[{"category": "Languages", "items": ["Python", "SQL"]}],
        projects=[],
    )


def _requirements() -> JobRequirements:
    # Resume has Python/PyTorch but NOT Kubernetes -> Kubernetes is a gap.
    return JobRequirements(
        hard_skills=[
            RequirementItem(term="Python", weight=1.0, evidence="Python required"),
            RequirementItem(term="Kubernetes", weight=0.9, evidence="Kubernetes experience"),
        ],
        soft_skills=[],
        domain_terms=[],
        seniority="senior",
        must_haves=["Python"],
        nice_to_haves=["Kubernetes"],
    )


async def _user_and_profile(session: AsyncSession) -> tuple[User, Profile]:
    user = User(email=f"me-{datetime.now(UTC).timestamp()}@example.com")
    session.add(user)
    await session.commit()
    profile = Profile(user_id=user.id, data=_resume().model_dump(mode="json"), is_canonical=True)
    session.add(profile)
    await session.commit()
    return user, profile


async def _board(
    session: AsyncSession,
    company: str = "Acme AI",
    *,
    user_id: uuid.UUID | None = None,
) -> SourceBoard:
    """A source board. ``user_id=None`` (the default) is a system/seed board
    watched for everyone; pass a user_id for a user-owned board."""
    board = SourceBoard(
        source=SourceKind.greenhouse,
        identifier="acme",
        company_name=company,
        user_id=user_id,
    )
    session.add(board)
    await session.commit()
    return board


async def _posting(
    session: AsyncSession,
    board: SourceBoard,
    *,
    external_id: str,
    title: str = "ML Engineer",
    desc: str = "We need Python and Kubernetes.",
    location: str | None = "Remote",
    department: str | None = "ML",
    posted_at: datetime | None = None,
    requirements: JobRequirements | None = None,
) -> Posting:
    posting = Posting(
        source_board_id=board.id,
        external_id=external_id,
        title=title,
        location=location,
        department=department,
        url=f"https://x/{external_id}",
        description_text=desc,
        posted_at=posted_at,
        content_hash=content_hash(title, desc),
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        is_active=True,
        extracted_requirements=(requirements.model_dump(mode="json") if requirements else None),
    )
    session.add(posting)
    await session.commit()
    return posting


# --- score_posting_for_search unit test -------------------------------------


async def test_score_posting_reuses_phase1_scorer(session: AsyncSession) -> None:
    _, profile = await _user_and_profile(session)
    board = await _board(session)
    # Requirements pre-cached on the posting -> no LLM call needed here.
    posting = await _posting(session, board, external_id="p1", requirements=_requirements())
    search = SavedSearch(user_id=profile.user_id, name="AI/ML", profile_id=profile.id)

    result = await score_posting_for_search(session, posting, search)

    assert 0.0 <= result.score <= 100.0
    # Resume covers Python but not Kubernetes -> Kubernetes surfaces as a gap.
    assert "Kubernetes" in result.missing_terms
    assert "Python" not in result.missing_terms


# --- Recompute-skip / LLM call counting -------------------------------------


@pytest.fixture
def counted_extract(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Replace the one LLM path with a counter; assert extraction frequency."""
    calls = [0]

    async def _fake(raw_jd: str, model: str | None = None):
        calls[0] += 1
        return _requirements(), LLMUsage(input_tokens=1, output_tokens=1)

    monkeypatch.setattr(matching, "extract_requirements", _fake)
    return calls


async def test_unchanged_posting_does_not_re_extract_or_recompute(
    session: AsyncSession, counted_extract: list[int]
) -> None:
    _, profile = await _user_and_profile(session)
    board = await _board(session)
    await _posting(session, board, external_id="p1")  # no cached requirements
    search = SavedSearch(user_id=profile.user_id, name="AI/ML", profile_id=profile.id)
    session.add(search)
    await session.commit()

    first = await refresh_matches_for_search(session, search)
    assert (first.computed, first.skipped) == (1, 0)
    assert counted_extract[0] == 1  # extracted once

    second = await refresh_matches_for_search(session, search)
    assert (second.computed, second.skipped) == (0, 1)  # nothing changed
    assert counted_extract[0] == 1  # NO new LLM call


async def test_content_change_triggers_recompute(
    session: AsyncSession, counted_extract: list[int]
) -> None:
    _, profile = await _user_and_profile(session)
    board = await _board(session)
    posting = await _posting(session, board, external_id="p1")
    search = SavedSearch(user_id=profile.user_id, name="AI/ML", profile_id=profile.id)
    session.add(search)
    await session.commit()

    await refresh_matches_for_search(session, search)
    assert counted_extract[0] == 1

    # Simulate what the storage layer does on a real content change.
    posting.content_hash = content_hash(posting.title, "Totally new description.")
    posting.description_text = "Totally new description."
    posting.extracted_requirements = None
    await session.commit()

    stats = await refresh_matches_for_search(session, search)
    assert stats.computed == 1  # recomputed
    assert counted_extract[0] == 2  # re-extracted


# --- Filters + min_score + ordering in the matches query --------------------


async def _match(
    session: AsyncSession,
    search: SavedSearch,
    posting: Posting,
    score: float,
) -> None:
    session.add(
        PostingMatch(
            posting_id=posting.id,
            saved_search_id=search.id,
            score=score,
            missing_terms=[],
            computed_at=datetime.now(UTC),
            scored_content_hash=posting.content_hash,
            scored_profile_id=search.profile_id,
        )
    )
    await session.commit()


async def test_list_matches_applies_filters_min_score_and_ordering(
    session: AsyncSession,
) -> None:
    _, profile = await _user_and_profile(session)
    board = await _board(session)
    search = SavedSearch(
        user_id=profile.user_id,
        name="Remote ML",
        profile_id=profile.id,
        min_score=75.0,
        filters={"locations": ["remote"], "departments": ["ML"]},
    )
    session.add(search)
    await session.commit()

    now = datetime.now(UTC)
    keep_new = await _posting(
        session,
        board,
        external_id="a",
        location="Remote - US",
        department="ML",
        posted_at=now,
    )
    keep_old = await _posting(
        session,
        board,
        external_id="b",
        location="Remote",
        department="ML",
        posted_at=now - timedelta(days=5),
    )
    low_score = await _posting(
        session, board, external_id="c", location="Remote", department="ML", posted_at=now
    )
    wrong_loc = await _posting(
        session, board, external_id="d", location="Onsite NYC", department="ML", posted_at=now
    )
    wrong_dept = await _posting(
        session, board, external_id="e", location="Remote", department="Sales", posted_at=now
    )

    await _match(session, search, keep_new, 90.0)
    await _match(session, search, keep_old, 80.0)
    await _match(session, search, low_score, 50.0)  # below min_score
    await _match(session, search, wrong_loc, 95.0)  # wrong location
    await _match(session, search, wrong_dept, 95.0)  # wrong department

    results = await list_matches(session, search.id)

    ids = [r.posting_id for r in results]
    assert ids == [keep_new.id, keep_old.id]  # filtered + newest posted_at first
    assert all(r.company_name == "Acme AI" for r in results)


# --- Ownership scoping: own boards + system boards only ---------------------


async def _match_ids(session: AsyncSession, search: SavedSearch) -> set[uuid.UUID]:
    rows = (
        await session.execute(
            select(PostingMatch.posting_id).where(PostingMatch.saved_search_id == search.id)
        )
    ).scalars()
    return set(rows)


async def test_refresh_and_list_scope_to_owner_plus_system_boards(
    session: AsyncSession, counted_extract: list[int]
) -> None:
    """Two users, each with their own board+posting, plus one system board.
    User A's search scores/surfaces its own + the system posting, never B's."""
    user_a, profile_a = await _user_and_profile(session)
    user_b, profile_b = await _user_and_profile(session)

    board_a = await _board(session, "A Co", user_id=user_a.id)
    board_b = await _board(session, "B Co", user_id=user_b.id)
    system_board = await _board(session, "System Co", user_id=None)

    posting_a = await _posting(session, board_a, external_id="a")
    posting_b = await _posting(session, board_b, external_id="b")
    posting_sys = await _posting(session, system_board, external_id="s")

    search_a = SavedSearch(
        user_id=user_a.id, name="A", profile_id=profile_a.id, min_score=0.0
    )
    session.add(search_a)
    await session.commit()

    await refresh_matches_for_search(session, search_a)

    # Scoring never even creates an out-of-scope row for user B's board.
    scored = await _match_ids(session, search_a)
    assert posting_a.id in scored
    assert posting_sys.id in scored
    assert posting_b.id not in scored

    ids = {r.posting_id for r in await list_matches(session, search_a.id)}
    assert ids == {posting_a.id, posting_sys.id}

    # The system board's posting is visible to user B's search too.
    search_b = SavedSearch(
        user_id=user_b.id, name="B", profile_id=profile_b.id, min_score=0.0
    )
    session.add(search_b)
    await session.commit()
    await refresh_matches_for_search(session, search_b)
    ids_b = {r.posting_id for r in await list_matches(session, search_b.id)}
    assert ids_b == {posting_b.id, posting_sys.id}
    assert posting_a.id not in ids_b


async def test_list_matches_filters_out_of_scope_rows_defense_in_depth(
    session: AsyncSession,
) -> None:
    """Even if an out-of-scope match row already exists (a prior buggy run),
    list_matches must not surface it — the ownership join is applied at read
    time, not only at scoring time."""
    user_a, profile_a = await _user_and_profile(session)
    user_b, _profile_b = await _user_and_profile(session)
    board_b = await _board(session, "B Co", user_id=user_b.id)
    posting_b = await _posting(session, board_b, external_id="b")

    search_a = SavedSearch(
        user_id=user_a.id, name="A", profile_id=profile_a.id, min_score=0.0
    )
    session.add(search_a)
    await session.commit()

    # Simulate a stale, out-of-scope row written before the invariant existed.
    await _match(session, search_a, posting_b, 95.0)

    results = await list_matches(session, search_a.id)
    assert results == []


async def test_unwatching_board_removes_its_postings_from_matches_immediately(
    session: AsyncSession,
) -> None:
    """Deleting a user's own source_board drops its postings from the feed on the
    very next query — no separate cleanup pass for the unwatch case."""
    user_a, profile_a = await _user_and_profile(session)
    board_a = await _board(session, "A Co", user_id=user_a.id)
    posting_a = await _posting(session, board_a, external_id="a")

    search_a = SavedSearch(
        user_id=user_a.id, name="A", profile_id=profile_a.id, min_score=0.0
    )
    session.add(search_a)
    await session.commit()
    await _match(session, search_a, posting_a, 95.0)

    assert {r.posting_id for r in await list_matches(session, search_a.id)} == {posting_a.id}

    await session.delete(board_a)  # user unwatches the board
    await session.commit()

    assert await list_matches(session, search_a.id) == []
