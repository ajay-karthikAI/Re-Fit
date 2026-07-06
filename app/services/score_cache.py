from datetime import UTC, datetime
from typing import Any
import uuid

from app.schemas.score import ATSScore


def build_score_cache(job_target_id: uuid.UUID, score: ATSScore) -> dict[str, Any]:
    return {
        "job_target_id": str(job_target_id),
        "score": score.model_dump(mode="json"),
        "headline_score": score.headline_score,
        "cached_at": datetime.now(UTC).isoformat(),
    }


def headline_from_cache(score_cache: dict[str, Any] | None) -> float | None:
    if not score_cache:
        return None
    value = score_cache.get("headline_score")
    if value is not None:
        return float(value)
    score = score_cache.get("score")
    if isinstance(score, dict) and score.get("headline_score") is not None:
        return float(score["headline_score"])
    return None
