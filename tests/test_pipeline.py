import pytest
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import dispose_engine
from app.models import JobTarget, PipelineRun, PipelineRunStatus, Upload, User
from app.services import pipeline


async def test_pipeline_failure_records_original_exception(
    session: AsyncSession, monkeypatch: MonkeyPatch
) -> None:
    user = User(email="pipeline-failure@example.com")
    session.add(user)
    await session.flush()
    upload = Upload(
        user_id=user.id,
        s3_key="tests/failure/resume.pdf",
        filename="resume.pdf",
        source_format="pdf",
    )
    job_target = JobTarget(
        user_id=user.id,
        raw_description="A job description that will never be reached.",
        company="Failure Co",
        title="Failure Target",
    )
    session.add_all([upload, job_target])
    await session.commit()

    async def fail_parse(*args: object, **kwargs: object) -> None:
        raise RuntimeError("parse exploded")

    monkeypatch.setattr(pipeline, "parse_upload", fail_parse)

    try:
        with pytest.raises(RuntimeError, match="parse exploded"):
            await pipeline.run_full_pipeline_async(user.id, upload.id, job_target.id)
    finally:
        await dispose_engine()

    result = await session.execute(select(PipelineRun).where(PipelineRun.user_id == user.id))
    run = result.scalar_one()
    assert run.status == PipelineRunStatus.failed
    assert run.error == "parse exploded"
