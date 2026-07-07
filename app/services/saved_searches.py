import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Profile, SavedSearch
from app.models import Digest
from app.schemas.saved_search import (
    PostingMatchRead,
    SavedSearchCreate,
    SavedSearchUpdate,
)
from app.services.digest import list_digests as _list_digests
from app.services.errors import NotFoundError
from app.services.matching import list_matches, refresh_matches_for_search
from app.services.users import get_user


async def create_saved_search(session: AsyncSession, payload: SavedSearchCreate) -> SavedSearch:
    await get_user(session, payload.user_id)
    profile = await session.get(Profile, payload.profile_id)
    if profile is None or profile.user_id != payload.user_id:
        raise NotFoundError(f"profile {payload.profile_id} not found for this user")

    saved_search = SavedSearch(
        user_id=payload.user_id,
        name=payload.name,
        profile_id=payload.profile_id,
        min_score=payload.min_score,
        filters=payload.filters.model_dump(mode="json") if payload.filters else None,
    )
    session.add(saved_search)
    await session.commit()
    await session.refresh(saved_search)
    return saved_search


async def list_saved_searches(session: AsyncSession, user_id: uuid.UUID) -> list[SavedSearch]:
    await get_user(session, user_id)
    result = await session.execute(
        select(SavedSearch)
        .where(SavedSearch.user_id == user_id)
        .order_by(SavedSearch.created_at.desc())
    )
    return list(result.scalars().all())


async def get_saved_search(session: AsyncSession, saved_search_id: uuid.UUID) -> SavedSearch:
    saved_search = await session.get(SavedSearch, saved_search_id)
    if saved_search is None:
        raise NotFoundError(f"saved search {saved_search_id} not found")
    return saved_search


async def update_saved_search(
    session: AsyncSession, saved_search_id: uuid.UUID, payload: SavedSearchUpdate
) -> SavedSearch:
    saved_search = await get_saved_search(session, saved_search_id)
    if payload.is_active is not None:
        saved_search.is_active = payload.is_active
    if payload.min_score is not None:
        saved_search.min_score = payload.min_score
    await session.commit()
    await session.refresh(saved_search)
    return saved_search


async def get_matches(session: AsyncSession, saved_search_id: uuid.UUID) -> list[PostingMatchRead]:
    """Refresh scores for any new/changed postings, then return those clearing
    the score bar. Refresh is a no-op for postings already scored current."""
    saved_search = await get_saved_search(session, saved_search_id)
    await refresh_matches_for_search(session, saved_search)
    return await list_matches(session, saved_search_id)


async def list_digests_for_search(
    session: AsyncSession, saved_search_id: uuid.UUID
) -> list[Digest]:
    return await _list_digests(session, saved_search_id)
