import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application, JobTarget, Profile, ResumeVersion
from app.schemas.application import (
    ApplicationCreate,
    ApplicationListItem,
    ApplicationRead,
    ApplicationUpdate,
)
from app.services.errors import NotFoundError
from app.services.users import get_user


async def _get_owned_version(
    session: AsyncSession, user_id: uuid.UUID, resume_version_id: uuid.UUID
) -> ResumeVersion:
    """Fetch a resume version, requiring that its profile belongs to this user."""
    result = await session.execute(
        select(ResumeVersion)
        .join(Profile, ResumeVersion.profile_id == Profile.id)
        .where(ResumeVersion.id == resume_version_id, Profile.user_id == user_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise NotFoundError(f"resume version {resume_version_id} not found for user {user_id}")
    return version


async def create_application(
    session: AsyncSession, user_id: uuid.UUID, payload: ApplicationCreate
) -> Application:
    await get_user(session, user_id)

    job_target = await session.get(JobTarget, payload.job_target_id)
    if job_target is None or job_target.user_id != user_id:
        raise NotFoundError(f"job target {payload.job_target_id} not found for user {user_id}")

    await _get_owned_version(session, user_id, payload.resume_version_id)

    application = Application(
        user_id=user_id,
        job_target_id=payload.job_target_id,
        resume_version_id=payload.resume_version_id,
        status=payload.status,
    )
    session.add(application)
    await session.commit()
    await session.refresh(application)
    return application


async def update_application(
    session: AsyncSession, application_id: uuid.UUID, payload: ApplicationUpdate
) -> Application:
    application = await session.get(Application, application_id)
    if application is None:
        raise NotFoundError(f"application {application_id} not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(application, field, value)
    await session.commit()
    await session.refresh(application)
    return application


async def list_applications(session: AsyncSession, user_id: uuid.UUID) -> list[ApplicationListItem]:
    await get_user(session, user_id)
    result = await session.execute(
        select(Application, JobTarget.company, JobTarget.title, ResumeVersion.label)
        .join(JobTarget, Application.job_target_id == JobTarget.id)
        .join(ResumeVersion, Application.resume_version_id == ResumeVersion.id)
        .where(Application.user_id == user_id)
        .order_by(Application.created_at.desc())
    )
    return [
        ApplicationListItem(
            **ApplicationRead.model_validate(application).model_dump(),
            company=company,
            title=title,
            resume_version_label=label,
        )
        for application, company, title, label in result.all()
    ]
