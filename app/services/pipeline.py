"""Full Phase 1 pipeline orchestration."""

import asyncio
from time import monotonic
import uuid
from typing import Any

import anyio.to_thread
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session_factory
from app.models import (
    JobTarget,
    PipelineRun,
    PipelineRunStatus,
    Profile,
    ResumeVersion,
    Upload,
)
from app.schemas.jd import JobRequirements
from app.schemas.llm import LLMUsage
from app.schemas.render import RenderRequest
from app.schemas.resume import StructuredResume
from app.services.embeddings import populate_embeddings
from app.services.errors import ConflictError, NotFoundError
from app.services.jd import extract_requirements
from app.services.render import render_version_document
from app.services.score import score_resume
from app.services.score_cache import build_score_cache
from app.services.tailor import tailor
from app.services.uploads import parse_upload


def _as_uuid(value: uuid.UUID | str) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


def _usage_dict(usage: LLMUsage) -> dict[str, int]:
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.input_tokens + usage.output_tokens,
    }


def _estimated_cost(usage: LLMUsage) -> float | None:
    settings = get_settings()
    if not settings.llm_input_cost_per_million and not settings.llm_output_cost_per_million:
        return None
    cost = (usage.input_tokens / 1_000_000) * settings.llm_input_cost_per_million + (
        usage.output_tokens / 1_000_000
    ) * settings.llm_output_cost_per_million
    return round(cost, 6)


async def create_pipeline_run(
    session: AsyncSession, upload_id: uuid.UUID, job_target_id: uuid.UUID
) -> PipelineRun:
    upload = await session.get(Upload, upload_id)
    if upload is None:
        raise NotFoundError(f"upload {upload_id} not found")

    job_target = await session.get(JobTarget, job_target_id)
    if job_target is None or job_target.user_id != upload.user_id:
        raise NotFoundError(f"job target {job_target_id} not found for this upload's user")

    run = PipelineRun(
        user_id=upload.user_id,
        upload_id=upload.id,
        job_target_id=job_target.id,
        status=PipelineRunStatus.pending,
        stage="pending",
        timings={},
        results=None,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def get_pipeline_run(session: AsyncSession, run_id: uuid.UUID) -> PipelineRun:
    run = await session.get(PipelineRun, run_id)
    if run is None:
        raise NotFoundError(f"pipeline run {run_id} not found")
    return run


async def _commit_run(
    session: AsyncSession,
    run: PipelineRun,
    *,
    status: PipelineRunStatus | None = None,
    stage: str | None = None,
    error: str | None = None,
    timings: dict[str, float] | None = None,
    results: dict[str, Any] | None = None,
) -> None:
    if status is not None:
        run.status = status
    if stage is not None:
        run.stage = stage
    run.error = error
    if timings is not None:
        run.timings = timings
    if results is not None:
        run.results = results
    await session.commit()
    await session.refresh(run)


async def _record_stage(
    session: AsyncSession,
    run: PipelineRun,
    stage: str,
    timings: dict[str, float],
) -> float:
    await _commit_run(
        session,
        run,
        status=PipelineRunStatus.running,
        stage=stage,
        timings=timings,
    )
    return monotonic()


async def _finish_stage(
    session: AsyncSession,
    run: PipelineRun,
    stage: str,
    started_at: float,
    timings: dict[str, float],
) -> None:
    timings[stage] = round(monotonic() - started_at, 3)
    await _commit_run(session, run, stage=stage, timings=timings)


async def _requirements_for_job(
    session: AsyncSession,
    job_target: JobTarget,
) -> tuple[JobRequirements, LLMUsage, bool]:
    if job_target.extracted_requirements is not None:
        return JobRequirements.model_validate(job_target.extracted_requirements), LLMUsage(), True

    requirements, usage = await extract_requirements(job_target.raw_description)
    job_target.extracted_requirements = requirements.model_dump(mode="json")
    await session.commit()
    await session.refresh(job_target)
    return requirements, usage, False


async def run_full_pipeline_async(
    user_id: uuid.UUID | str,
    upload_id: uuid.UUID | str,
    job_target_id: uuid.UUID | str,
    *,
    run_id: uuid.UUID | str | None = None,
) -> dict[str, Any]:
    user_uuid = _as_uuid(user_id)
    upload_uuid = _as_uuid(upload_id)
    job_uuid = _as_uuid(job_target_id)
    run_uuid = _as_uuid(run_id) if run_id is not None else None

    async with get_session_factory()() as session:
        run = (
            await get_pipeline_run(session, run_uuid)
            if run_uuid is not None
            else await create_pipeline_run(session, upload_uuid, job_uuid)
        )
        if (
            run.user_id != user_uuid
            or run.upload_id != upload_uuid
            or run.job_target_id != job_uuid
        ):
            raise NotFoundError("pipeline run does not match supplied user/upload/job target")

        timings = dict(run.timings or {})
        total_usage = LLMUsage()
        requirements_cached = False

        try:
            started = await _record_stage(session, run, "parse_resume", timings)
            parse_result = await parse_upload(session, upload_uuid)
            total_usage += parse_result.usage
            profile = (
                (
                    await session.execute(
                        select(Profile).where(Profile.user_id == user_uuid, Profile.is_canonical)
                    )
                )
                .scalars()
                .one_or_none()
            )
            if profile is None:
                raise NotFoundError(f"user {user_uuid} has no canonical profile after parsing")
            await _finish_stage(session, run, "parse_resume", started, timings)

            started = await _record_stage(session, run, "extract_requirements", timings)
            job_target = await session.get(JobTarget, job_uuid)
            if job_target is None or job_target.user_id != user_uuid:
                raise NotFoundError(f"job target {job_uuid} not found for user {user_uuid}")
            requirements, jd_usage, requirements_cached = await _requirements_for_job(
                session, job_target
            )
            total_usage += jd_usage
            await _finish_stage(session, run, "extract_requirements", started, timings)

            started = await _record_stage(session, run, "embeddings", timings)
            source_version = ResumeVersion(
                profile_id=profile.id,
                job_target_id=None,
                data=profile.data,
                diff=None,
                label=f"Pipeline source {run.id}",
            )
            session.add(source_version)
            await session.commit()
            await session.refresh(source_version)
            embedded_count = await populate_embeddings(session, source_version.id)
            await _finish_stage(session, run, "embeddings", started, timings)

            started = await _record_stage(session, run, "tailor", timings)
            profile_resume = StructuredResume.model_validate(profile.data)
            tailor_result = await tailor(profile_resume, requirements)
            total_usage += tailor_result.stats.usage
            score_before, score_after = await anyio.to_thread.run_sync(
                lambda: (
                    score_resume(profile_resume, requirements),
                    score_resume(tailor_result.resume, requirements),
                )
            )
            version = ResumeVersion(
                profile_id=profile.id,
                job_target_id=job_uuid,
                data=tailor_result.resume.model_dump(mode="json"),
                score_cache=build_score_cache(job_uuid, score_after),
                diff={
                    "changes": [entry.model_dump(mode="json") for entry in tailor_result.diff],
                    "stats": tailor_result.stats.model_dump(mode="json"),
                    "discarded_rewrites": [
                        rewrite.model_dump(mode="json")
                        for rewrite in tailor_result.discarded_rewrites
                    ],
                    "score_before": score_before.model_dump(mode="json"),
                    "score_after": score_after.model_dump(mode="json"),
                },
                label=f"Pipeline tailored for {job_target.company or job_target.title or 'job target'}",
            )
            session.add(version)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ConflictError(
                    f"a resume version for job target {job_uuid} already exists on this profile"
                ) from exc
            await session.refresh(version)
            await _finish_stage(session, run, "tailor", started, timings)

            started = await _record_stage(session, run, "render_pdf", timings)
            render_response = await render_version_document(
                session,
                version.id,
                RenderRequest(format="pdf"),
            )
            await _finish_stage(session, run, "render_pdf", started, timings)

            usage = _usage_dict(total_usage)
            results = {
                "version_id": str(version.id),
                "source_version_id": str(source_version.id),
                "document_id": str(render_response.document_id),
                "download_url": render_response.download_url,
                "s3_key": render_response.s3_key,
                "scores": {
                    "before": score_before.model_dump(mode="json"),
                    "after": score_after.model_dump(mode="json"),
                },
                "diff": [entry.model_dump(mode="json") for entry in tailor_result.diff],
                "rewrite_stats": tailor_result.stats.model_dump(mode="json"),
                "discarded_rewrites": [
                    rewrite.model_dump(mode="json") for rewrite in tailor_result.discarded_rewrites
                ],
                "requirements_cached": requirements_cached,
                "embedded_bullets": embedded_count,
                "pipeline_timings": timings,
                "token_usage": usage,
                "estimated_cost_usd": _estimated_cost(total_usage),
                "render_warnings": render_response.warnings,
            }
            await _commit_run(
                session,
                run,
                status=PipelineRunStatus.succeeded,
                stage="succeeded",
                timings=timings,
                results=results,
            )
            return results
        except Exception as exc:
            await session.rollback()
            failed_run = await get_pipeline_run(session, run.id)
            await _commit_run(
                session,
                failed_run,
                status=PipelineRunStatus.failed,
                stage=failed_run.stage or "failed",
                error=str(exc),
                timings=timings,
            )
            raise


def run_full_pipeline(
    user_id: uuid.UUID | str,
    upload_id: uuid.UUID | str,
    job_target_id: uuid.UUID | str,
    *,
    run_id: uuid.UUID | str | None = None,
) -> dict[str, Any]:
    return asyncio.run(run_full_pipeline_async(user_id, upload_id, job_target_id, run_id=run_id))
