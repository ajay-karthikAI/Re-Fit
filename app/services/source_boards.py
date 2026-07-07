import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source_board import BoardHealth, SourceBoard
from app.schemas.source_board import SourceBoardCreate
from app.services.errors import NotFoundError
from app.services.sources.registry import client_for


async def create_source_board(session: AsyncSession, payload: SourceBoardCreate) -> SourceBoard:
    """Register a board, validating it with one live fetch first.

    We call the source client directly (not ``fetch_board``, which swallows
    failures) so a 404/unreachable feed surfaces *now* as a ``SourceError`` —
    the router turns that into a 422 so the user gets instant feedback instead
    of a board that silently never returns anything.
    """
    client = client_for(payload.source)
    await client.list_postings(payload.identifier)  # raises SourceError on a bad board

    now = datetime.now(UTC)
    board = SourceBoard(
        user_id=payload.user_id,
        source=payload.source,
        identifier=payload.identifier,
        company_name=payload.company_name,
        health=BoardHealth.healthy,
        consecutive_failures=0,
        last_checked_at=now,
        last_success_at=now,
    )
    session.add(board)
    await session.commit()
    await session.refresh(board)
    return board


async def list_source_boards(session: AsyncSession) -> list[SourceBoard]:
    # Surface ailing boards first: highest failure streak on top, so a board
    # silently dying is the first thing you see, not buried by creation order.
    result = await session.execute(
        select(SourceBoard).order_by(
            SourceBoard.consecutive_failures.desc(), SourceBoard.created_at.desc()
        )
    )
    return list(result.scalars().all())


async def delete_source_board(session: AsyncSession, board_id: uuid.UUID) -> None:
    board = await session.get(SourceBoard, board_id)
    if board is None:
        raise NotFoundError(f"source board {board_id} not found")
    await session.delete(board)
    await session.commit()
