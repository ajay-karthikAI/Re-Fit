from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

PipelineStatus = Literal["pending", "running", "succeeded", "failed"]


class PipelineRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: UUID
    job_target_id: UUID


class PipelineRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    upload_id: UUID
    job_target_id: UUID
    status: PipelineStatus
    stage: str
    error: str | None
    timings: dict[str, Any]
    results: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
