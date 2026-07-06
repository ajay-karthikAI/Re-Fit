import uuid

from fastapi import APIRouter

from app.routers.deps import SessionDep
from app.schemas.application import ApplicationRead, ApplicationUpdate
from app.services import applications

router = APIRouter(tags=["applications"])


@router.patch("/applications/{application_id}")
async def update_application(
    application_id: uuid.UUID, payload: ApplicationUpdate, session: SessionDep
) -> ApplicationRead:
    return await applications.update_application(session, application_id, payload)  # type: ignore[return-value]
