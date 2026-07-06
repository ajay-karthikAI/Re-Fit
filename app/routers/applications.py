import uuid

from fastapi import APIRouter

from app.routers.deps import SessionDep
from app.schemas.application import ApplicationRead, ApplicationUpdate
from app.schemas.followup import FollowupRead, FollowupRequest, FollowupResult
from app.schemas.kit import ApplicationKitDetail
from app.services import applications, followup, kit

router = APIRouter(tags=["applications"])


@router.patch("/applications/{application_id}")
async def update_application(
    application_id: uuid.UUID, payload: ApplicationUpdate, session: SessionDep
) -> ApplicationRead:
    return await applications.update_application(session, application_id, payload)  # type: ignore[return-value]


@router.get("/applications/{application_id}/kit")
async def get_application_kit(
    application_id: uuid.UUID, session: SessionDep
) -> ApplicationKitDetail:
    return await kit.get_application_kit_detail(session, application_id)


@router.post("/applications/{application_id}/followups")
async def create_followup(
    application_id: uuid.UUID,
    payload: FollowupRequest,
    session: SessionDep,
) -> FollowupResult:
    return await followup.create_followup_for_application(session, application_id, payload)


@router.get("/applications/{application_id}/followups")
async def list_followups(
    application_id: uuid.UUID,
    session: SessionDep,
) -> list[FollowupRead]:
    rows = await followup.list_followups_for_application(session, application_id)
    return [FollowupRead.model_validate(row) for row in rows]
