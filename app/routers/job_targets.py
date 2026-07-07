import uuid

from fastapi import APIRouter, status

from app.routers.deps import SessionDep
from app.schemas.application import ApplicationRead
from app.schemas.apply_kit import ApplyKit, ApplyKitRegenerateRequest, TrackRequest
from app.schemas.cover_letter import CoverLetterRequest, CoverLetterResult
from app.schemas.jd import JDExtractionResult
from app.schemas.job_target import JobTargetFromPosting, JobTargetRead
from app.schemas.kit import KitRequest, KitResult
from app.schemas.render import RenderRequest, RenderResponse
from app.schemas.short_answer import ShortAnswerRead, ShortAnswerRequest, ShortAnswerResult
from app.services import apply_kit, applications, cover_letter, job_targets, kit, short_answers

router = APIRouter(tags=["job-targets"])


@router.post("/postings/{posting_id}/job-target", status_code=status.HTTP_201_CREATED)
async def create_job_target_from_posting(
    posting_id: uuid.UUID, payload: JobTargetFromPosting, session: SessionDep
) -> JobTargetRead:
    """One-click bridge from a matched feed posting to a tailorable job target."""
    return await job_targets.create_job_target_from_posting(  # type: ignore[return-value]
        session, posting_id, payload.user_id
    )


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


@router.post("/job-targets/{job_target_id}/short-answers")
async def generate_short_answer(
    job_target_id: uuid.UUID,
    payload: ShortAnswerRequest,
    session: SessionDep,
) -> ShortAnswerResult:
    return await short_answers.generate_short_answer_for_job(session, job_target_id, payload)


@router.get("/job-targets/{job_target_id}/short-answers")
async def list_short_answers(
    job_target_id: uuid.UUID, session: SessionDep
) -> list[ShortAnswerRead]:
    return await short_answers.list_short_answers_for_job(session, job_target_id)  # type: ignore[return-value]


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


@router.get("/job-targets/{job_target_id}/apply-kit")
async def get_apply_kit(job_target_id: uuid.UUID, session: SessionDep) -> ApplyKit:
    return await apply_kit.assemble_apply_kit(session, job_target_id)


@router.post("/job-targets/{job_target_id}/apply-kit/regenerate")
async def regenerate_apply_kit_field(
    job_target_id: uuid.UUID,
    payload: ApplyKitRegenerateRequest,
    session: SessionDep,
) -> ApplyKit:
    return await apply_kit.regenerate_apply_kit_field(session, job_target_id, payload.field_key)


@router.post("/job-targets/{job_target_id}/track")
async def track(
    job_target_id: uuid.UUID, payload: TrackRequest, session: SessionDep
) -> ApplicationRead:
    return await applications.track_job_target(session, job_target_id, payload)  # type: ignore[return-value]
