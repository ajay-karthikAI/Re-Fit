import uuid

from fastapi import APIRouter, status

from app.routers.deps import SessionDep
from app.schemas.pipeline import PipelineRunCreate, PipelineRunRead
from app.services import pipeline as pipeline_service
from app.worker import run_full_pipeline_task

router = APIRouter(tags=["pipeline"])


@router.post("/pipeline/runs", status_code=status.HTTP_202_ACCEPTED)
async def create_pipeline_run(payload: PipelineRunCreate, session: SessionDep) -> PipelineRunRead:
    run = await pipeline_service.create_pipeline_run(
        session, payload.upload_id, payload.job_target_id
    )
    run_full_pipeline_task.delay(
        str(run.id),
        str(run.user_id),
        str(run.upload_id),
        str(run.job_target_id),
    )
    return run  # type: ignore[return-value]


@router.get("/pipeline/runs/{run_id}")
async def get_pipeline_run(run_id: uuid.UUID, session: SessionDep) -> PipelineRunRead:
    return await pipeline_service.get_pipeline_run(session, run_id)  # type: ignore[return-value]
