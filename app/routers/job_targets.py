import uuid

from fastapi import APIRouter

from app.routers.deps import SessionDep
from app.schemas.cover_letter import CoverLetterRequest, CoverLetterResult
from app.schemas.jd import JDExtractionResult
from app.schemas.job_target import JobTargetRead
from app.schemas.kit import KitRequest, KitResult
from app.schemas.render import RenderRequest, RenderResponse
from app.services import cover_letter, job_targets, kit

router = APIRouter(tags=["job-targets"])


@router.get("/job-targets/{job_target_id}")
async def get_job_target(job_target_id: uuid.UUID, session: SessionDep) -> JobTargetRead:
    return await job_targets.get_job_target(session, job_target_id)  # type: ignore[return-value]


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


@router.post("/job-targets/{job_target_id}/kit")
async def create_or_get_kit(
    job_target_id: uuid.UUID,
    payload: KitRequest,
    session: SessionDep,
) -> KitResult:
    return await kit.create_or_get_kit(session, job_target_id, payload)


@router.get("/job-targets/{job_target_id}/kit")
async def get_kit(job_target_id: uuid.UUID, session: SessionDep) -> KitResult:
    return await kit.get_existing_kit(session, job_target_id)
