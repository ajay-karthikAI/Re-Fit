import uuid

from fastapi import APIRouter, status

from app.routers.deps import SessionDep
from app.schemas.profile import ResumeVersionCreate, ResumeVersionRead
from app.schemas.tailor import TailorRequest, TailorResult
from app.schemas.version_history import ResumeVersionListItem
from app.services import profiles, versions
from app.services import tailor as tailor_service

router = APIRouter(tags=["profiles"])


@router.post("/profiles/{profile_id}/versions", status_code=status.HTTP_201_CREATED)
async def create_version(
    profile_id: uuid.UUID, payload: ResumeVersionCreate, session: SessionDep
) -> ResumeVersionRead:
    return await profiles.create_version(  # type: ignore[return-value]
        session, profile_id, payload.job_target_id, payload.label
    )


@router.get("/profiles/{profile_id}/versions")
async def list_versions(
    profile_id: uuid.UUID,
    session: SessionDep,
) -> list[ResumeVersionListItem]:
    return await versions.list_profile_versions(session, profile_id)


@router.post("/profiles/{profile_id}/tailor")
async def tailor_profile(
    profile_id: uuid.UUID, payload: TailorRequest, session: SessionDep
) -> TailorResult:
    return await tailor_service.tailor_profile_for_job(session, profile_id, payload.job_target_id)
