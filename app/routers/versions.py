import uuid

from fastapi import APIRouter

from app.routers.deps import SessionDep
from app.schemas.render import RenderRequest, RenderResponse
from app.schemas.score import ATSScore
from app.services import render as render_service
from app.services import score as score_service

router = APIRouter(tags=["versions"])


@router.get("/versions/{version_id}/score")
async def score_version(
    version_id: uuid.UUID, job_target_id: uuid.UUID, session: SessionDep
) -> ATSScore:
    return await score_service.score_resume_version(session, version_id, job_target_id)


@router.post("/versions/{version_id}/render")
async def render_version(
    version_id: uuid.UUID, payload: RenderRequest, session: SessionDep
) -> RenderResponse:
    return await render_service.render_version_document(session, version_id, payload)
