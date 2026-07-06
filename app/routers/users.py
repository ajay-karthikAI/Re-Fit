import uuid

from fastapi import APIRouter, UploadFile, status

from app.routers.deps import SessionDep
from app.schemas.answer_profile import (
    AnswerProfileCompleteness,
    AnswerProfileRead,
    AnswerProfileWrite,
)
from app.schemas.application import ApplicationCreate, ApplicationListItem, ApplicationRead
from app.schemas.job_target import JobTargetCreate, JobTargetListItem, JobTargetRead
from app.schemas.profile import ProfileRead
from app.schemas.resume import StructuredResume
from app.schemas.upload import UploadResult
from app.schemas.user import UserCreate, UserRead
from app.services import answer_profile as answer_profile_service
from app.services import applications, job_targets, profiles, uploads, users

router = APIRouter(tags=["users"])


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, session: SessionDep) -> UserRead:
    return await users.create_user(session, payload.email)  # type: ignore[return-value]


@router.get("/users")
async def list_users(session: SessionDep) -> list[UserRead]:
    return await users.list_users(session)  # type: ignore[return-value]


@router.put("/users/{user_id}/profile")
async def upsert_profile(
    user_id: uuid.UUID, payload: StructuredResume, session: SessionDep
) -> ProfileRead:
    return await profiles.upsert_canonical_profile(session, user_id, payload)  # type: ignore[return-value]


@router.get("/users/{user_id}/profile")
async def get_profile(user_id: uuid.UUID, session: SessionDep) -> ProfileRead:
    return await profiles.get_canonical_profile(session, user_id)  # type: ignore[return-value]


@router.put("/users/{user_id}/answer-profile")
async def upsert_answer_profile(
    user_id: uuid.UUID, payload: AnswerProfileWrite, session: SessionDep
) -> AnswerProfileRead:
    return await answer_profile_service.upsert_answer_profile(  # type: ignore[return-value]
        session, user_id, payload
    )


@router.get("/users/{user_id}/answer-profile")
async def get_answer_profile(user_id: uuid.UUID, session: SessionDep) -> AnswerProfileRead:
    return await answer_profile_service.get_answer_profile(session, user_id)  # type: ignore[return-value]


@router.get("/users/{user_id}/answer-profile/completeness")
async def get_answer_profile_completeness(
    user_id: uuid.UUID, session: SessionDep
) -> AnswerProfileCompleteness:
    return await answer_profile_service.get_completeness(session, user_id)


@router.post("/users/{user_id}/job-targets", status_code=status.HTTP_201_CREATED)
async def create_job_target(
    user_id: uuid.UUID, payload: JobTargetCreate, session: SessionDep
) -> JobTargetRead:
    return await job_targets.create_job_target(session, user_id, payload)  # type: ignore[return-value]


@router.get("/users/{user_id}/job-targets")
async def list_job_targets(user_id: uuid.UUID, session: SessionDep) -> list[JobTargetListItem]:
    return await job_targets.list_job_targets(session, user_id)


@router.post("/users/{user_id}/applications", status_code=status.HTTP_201_CREATED)
async def create_application(
    user_id: uuid.UUID, payload: ApplicationCreate, session: SessionDep
) -> ApplicationRead:
    return await applications.create_application(session, user_id, payload)  # type: ignore[return-value]


@router.get("/users/{user_id}/applications")
async def list_applications(user_id: uuid.UUID, session: SessionDep) -> list[ApplicationListItem]:
    return await applications.list_applications(session, user_id)


@router.post("/users/{user_id}/uploads", status_code=status.HTTP_201_CREATED)
async def upload_resume(user_id: uuid.UUID, file: UploadFile, session: SessionDep) -> UploadResult:
    return await uploads.create_upload(session, user_id, file)
