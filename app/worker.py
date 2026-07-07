import asyncio
from collections.abc import Awaitable
from typing import TypeVar

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings
from app.db import dispose_engine, get_session_factory
from app.services.digest import send_daily_digests
from app.services.ingestion import (
    ingest_all_boards,
    rescore_active_searches,
    run_freshness_cleanup,
)
from app.services.pipeline import run_full_pipeline

settings = get_settings()

celery_app = Celery(
    "refit",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_track_started=True,
    worker_prefetch_multiplier=1,
    worker_pool="solo",
)

# Recurring ingestion pipeline. Ingestion runs every 6h; rescoring runs every 6h
# but offset one hour later so it scores what ingestion just wrote; freshness and
# the digest run once daily.
celery_app.conf.beat_schedule = {
    "ingest-all-boards": {
        "task": "app.worker.ingest_all_boards_task",
        "schedule": crontab(minute=0, hour="0,6,12,18"),
    },
    "rescore-active-searches": {
        "task": "app.worker.rescore_active_searches_task",
        "schedule": crontab(minute=0, hour="1,7,13,19"),  # +1h after ingestion
    },
    "freshness-cleanup": {
        "task": "app.worker.freshness_cleanup_task",
        "schedule": crontab(minute=0, hour=3),  # daily
    },
    "send-daily-digest": {
        "task": "app.worker.send_daily_digest_task",
        "schedule": crontab(minute=0, hour=settings.digest_hour),  # daily, configurable
    },
}

_T = TypeVar("_T")


def _run(coro: Awaitable[_T]) -> _T:
    """Run one async task body on a fresh event loop, disposing the engine after
    so the next Celery task (solo pool) doesn't reuse asyncpg connections bound to
    a now-closed loop."""

    async def _wrapped() -> _T:
        try:
            return await coro
        finally:
            await dispose_engine()

    return asyncio.run(_wrapped())


@celery_app.task(name="app.worker.run_full_pipeline_task")
def run_full_pipeline_task(
    run_id: str,
    user_id: str,
    upload_id: str,
    job_target_id: str,
) -> dict:
    return run_full_pipeline(user_id, upload_id, job_target_id, run_id=run_id)


@celery_app.task(name="app.worker.ingest_all_boards_task")
def ingest_all_boards_task() -> dict:
    return _run(ingest_all_boards())


@celery_app.task(name="app.worker.rescore_active_searches_task")
def rescore_active_searches_task() -> dict:
    return _run(rescore_active_searches())


@celery_app.task(name="app.worker.freshness_cleanup_task")
def freshness_cleanup_task() -> int:
    return _run(run_freshness_cleanup())


@celery_app.task(name="app.worker.send_daily_digest_task")
def send_daily_digest_task() -> int:
    async def _impl() -> int:
        async with get_session_factory()() as session:
            return await send_daily_digests(session)

    return _run(_impl())
