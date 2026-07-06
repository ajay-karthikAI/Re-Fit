from celery import Celery

from app.config import get_settings
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


@celery_app.task(name="app.worker.run_full_pipeline_task")
def run_full_pipeline_task(
    run_id: str,
    user_id: str,
    upload_id: str,
    job_target_id: str,
) -> dict:
    return run_full_pipeline(user_id, upload_id, job_target_id, run_id=run_id)
