import uuid

from fastapi import APIRouter

from app.routers.deps import SessionDep
from app.schemas.parse import ParseResult
from app.services import uploads

router = APIRouter(tags=["uploads"])


@router.post("/uploads/{upload_id}/parse")
async def parse_upload(upload_id: uuid.UUID, session: SessionDep) -> ParseResult:
    return await uploads.parse_upload(session, upload_id)
