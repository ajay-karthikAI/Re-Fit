import uuid

from fastapi import APIRouter, status

from app.routers.deps import SessionDep
from app.schemas.source_board import SourceBoardCreate, SourceBoardRead
from app.services import source_boards

router = APIRouter(tags=["source-boards"])


@router.post("/source-boards", status_code=status.HTTP_201_CREATED)
async def create_source_board(payload: SourceBoardCreate, session: SessionDep) -> SourceBoardRead:
    return await source_boards.create_source_board(session, payload)  # type: ignore[return-value]


@router.get("/source-boards")
async def list_source_boards(session: SessionDep) -> list[SourceBoardRead]:
    return await source_boards.list_source_boards(session)  # type: ignore[return-value]


@router.delete("/source-boards/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source_board(board_id: uuid.UUID, session: SessionDep) -> None:
    await source_boards.delete_source_board(session, board_id)
