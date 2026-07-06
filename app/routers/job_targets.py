import uuid

from fastapi import APIRouter

from app.routers.deps import SessionDep
from app.schemas.cover_letter import CoverLetterRequest, CoverLetterResult
from app.schemas.jd import JDExtractionResult
from app.schemas.render import RenderRequest, RenderResponse
from app.services import cover_letter, job_targets

router = APIRouter(tags=["job-targets"])


@router.post("/job-targets/{job_target_id}/extract")
async def extract_requirements(job_target_id: uuid.UUID, session: SessionDep) -> JDExtractionResult:
    return await job_targets.extract_and_store_requirements(session, job_target_id)


@router.post("/job-targets/{job_target_id}/cover-letter")
async def generate_cover_letter(
    job_target_id: uuid.UUID,
    payload: CoverLetterRequest,
    session: SessionDep,
) -> CoverLetterResult:
    return await cover_letter.generate_cover_letter_for_job(session, job_target_id, payload)


@router.post("/cover-letters/{cover_letter_id}/render")
async def render_cover_letter(
    cover_letter_id: uuid.UUID,
    payload: RenderRequest,
    session: SessionDep,
) -> RenderResponse:
    return await cover_letter.render_cover_letter_document(session, cover_letter_id, payload)
