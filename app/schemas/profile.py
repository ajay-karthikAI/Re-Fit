from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.resume import StructuredResume


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    data: StructuredResume
    is_canonical: bool
    created_at: datetime
    updated_at: datetime


class ResumeVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_target_id: UUID | None = None
    """None = a manual/base version not tied to a job target."""
    label: str | None = None


class ResumeVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    profile_id: UUID
    job_target_id: UUID | None
    data: StructuredResume
    diff: dict[str, Any] | None
    score_cache: dict[str, Any] | None = None
    label: str | None
    template_id: str
    template_variables: dict[str, Any]
    created_at: datetime
    deleted_at: datetime | None = None
