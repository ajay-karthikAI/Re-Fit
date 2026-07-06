import uuid

from fastapi import APIRouter, Response, status

from app.routers.deps import SessionDep
from app.schemas.render import RenderRequest, RenderResponse
from app.schemas.score import ATSScore
from app.schemas.version_history import EnrichedVersionDiff
from app.services import render as render_service
from app.services import score as score_service
from app.services import versions as version_service

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


@router.get("/versions/{version_id}/diff")
async def get_version_diff(version_id: uuid.UUID, session: SessionDep) -> EnrichedVersionDiff:
    return await version_service.get_enriched_diff(session, version_id)


@router.get("/versions/{from_version_id}/compare/{to_version_id}")
async def compare_versions(
    from_version_id: uuid.UUID,
    to_version_id: uuid.UUID,
    session: SessionDep,
) -> EnrichedVersionDiff:
    return await version_service.compare_versions(session, from_version_id, to_version_id)


@router.delete("/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(version_id: uuid.UUID, session: SessionDep) -> Response:
    await version_service.soft_delete_version(session, version_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
