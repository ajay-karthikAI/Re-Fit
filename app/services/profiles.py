import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobTarget, Profile, ResumeVersion
from app.schemas.resume import StructuredResume
from app.services.errors import ConflictError, NotFoundError
from app.services.users import get_user


async def upsert_canonical_profile(
    session: AsyncSession, user_id: uuid.UUID, resume: StructuredResume
) -> Profile:
    await get_user(session, user_id)
    result = await session.execute(
        select(Profile).where(Profile.user_id == user_id, Profile.is_canonical)
    )
    profile = result.scalar_one_or_none()
    data = resume.model_dump(mode="json")
    if profile is None:
        profile = Profile(user_id=user_id, data=data, is_canonical=True)
        session.add(profile)
    else:
        profile.data = data
    await session.commit()
    await session.refresh(profile)
    return profile


async def get_canonical_profile(session: AsyncSession, user_id: uuid.UUID) -> Profile:
    await get_user(session, user_id)
    result = await session.execute(
        select(Profile).where(Profile.user_id == user_id, Profile.is_canonical)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise NotFoundError(f"user {user_id} has no canonical profile")
    return profile


async def create_version(
    session: AsyncSession,
    profile_id: uuid.UUID,
    job_target_id: uuid.UUID | None,
    label: str | None,
) -> ResumeVersion:
    profile = await session.get(Profile, profile_id)
    if profile is None:
        raise NotFoundError(f"profile {profile_id} not found")

    if job_target_id is not None:
        job_target = await session.get(JobTarget, job_target_id)
        if job_target is None or job_target.user_id != profile.user_id:
            raise NotFoundError(f"job target {job_target_id} not found for this profile's user")

    # Phase 0: the version is a verbatim copy of the canonical data.
    # Tailoring (and the diff) arrives in Phase 1.
    version = ResumeVersion(
        profile_id=profile.id,
        job_target_id=job_target_id,
        data=profile.data,
        label=label,
    )
    session.add(version)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            f"a resume version for job target {job_target_id} already exists on this profile"
        ) from exc
    await session.refresh(version)
    return version
