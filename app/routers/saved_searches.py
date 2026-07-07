import uuid

from fastapi import APIRouter, status

from app.routers.deps import SessionDep
from app.schemas.saved_search import (
    DigestRead,
    PostingMatchRead,
    SavedSearchCreate,
    SavedSearchRead,
    SavedSearchUpdate,
)
from app.services import saved_searches

router = APIRouter(tags=["saved-searches"])


@router.post("/saved-searches", status_code=status.HTTP_201_CREATED)
async def create_saved_search(payload: SavedSearchCreate, session: SessionDep) -> SavedSearchRead:
    return await saved_searches.create_saved_search(session, payload)  # type: ignore[return-value]


@router.get("/saved-searches")
async def list_saved_searches(user_id: uuid.UUID, session: SessionDep) -> list[SavedSearchRead]:
    return await saved_searches.list_saved_searches(session, user_id)  # type: ignore[return-value]


@router.patch("/saved-searches/{saved_search_id}")
async def update_saved_search(
    saved_search_id: uuid.UUID, payload: SavedSearchUpdate, session: SessionDep
) -> SavedSearchRead:
    return await saved_searches.update_saved_search(  # type: ignore[return-value]
        session, saved_search_id, payload
    )


@router.get("/saved-searches/{saved_search_id}/matches")
async def get_matches(saved_search_id: uuid.UUID, session: SessionDep) -> list[PostingMatchRead]:
    return await saved_searches.get_matches(session, saved_search_id)


@router.get("/saved-searches/{saved_search_id}/digests")
async def list_digests(saved_search_id: uuid.UUID, session: SessionDep) -> list[DigestRead]:
    return await saved_searches.list_digests_for_search(session, saved_search_id)  # type: ignore[return-value]
