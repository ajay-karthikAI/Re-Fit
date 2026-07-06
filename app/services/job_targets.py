import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.ats_fields import detect_ats
from app.models import JobTarget, ResumeVersion
from app.schemas.jd import JDExtractionResult
from app.schemas.job_target import JobTargetCreate, JobTargetListItem
from app.services.errors import NotFoundError
from app.services.jd import extract_requirements
from app.services.users import get_user


async def create_job_target(
    session: AsyncSession, user_id: uuid.UUID, payload: JobTargetCreate
) -> JobTarget:
    await get_user(session, user_id)
    job_target = JobTarget(
        user_id=user_id,
        source_ats=detect_ats(payload.source_url),
        **payload.model_dump(),
    )
    session.add(job_target)
    await session.commit()
    await session.refresh(job_target)
    return job_target


async def get_job_target(session: AsyncSession, job_target_id: uuid.UUID) -> JobTarget:
    job_target = await session.get(JobTarget, job_target_id)
    if job_target is None:
        raise NotFoundError(f"job target {job_target_id} not found")
    return job_target


async def list_job_targets(session: AsyncSession, user_id: uuid.UUID) -> list[JobTargetListItem]:
    await get_user(session, user_id)
    has_kit = (
        select(ResumeVersion.id)
        .where(
            ResumeVersion.job_target_id == JobTarget.id,
            ResumeVersion.deleted_at.is_(None),
        )
        .exists()
    )
    result = await session.execute(
        select(JobTarget, has_kit.label("has_kit"))
        .where(JobTarget.user_id == user_id)
        .order_by(JobTarget.created_at.desc())
    )
    return [
        JobTargetListItem(
            id=job_target.id,
            company=job_target.company,
            title=job_target.title,
            source_url=job_target.source_url,
            created_at=job_target.created_at,
            has_requirements=job_target.extracted_requirements is not None,
            has_kit=kit_exists,
        )
        for job_target, kit_exists in result.all()
    ]


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
