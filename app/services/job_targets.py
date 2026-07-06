import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobTarget
from app.schemas.jd import JDExtractionResult
from app.schemas.job_target import JobTargetCreate
from app.services.errors import NotFoundError
from app.services.jd import extract_requirements
from app.services.users import get_user


async def create_job_target(
    session: AsyncSession, user_id: uuid.UUID, payload: JobTargetCreate
) -> JobTarget:
    await get_user(session, user_id)
    job_target = JobTarget(user_id=user_id, **payload.model_dump())
    session.add(job_target)
    await session.commit()
    await session.refresh(job_target)
    return job_target


async def extract_and_store_requirements(
    session: AsyncSession, job_target_id: uuid.UUID
) -> JDExtractionResult:
    job_target = await session.get(JobTarget, job_target_id)
    if job_target is None:
        raise NotFoundError(f"job target {job_target_id} not found")

    requirements, usage = await extract_requirements(job_target.raw_description)
    job_target.extracted_requirements = requirements.model_dump(mode="json")
    await session.commit()
    return JDExtractionResult(requirements=requirements, usage=usage)
