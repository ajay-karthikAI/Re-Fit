from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.application import ApplicationStatus


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_target_id: UUID
    resume_version_id: UUID
    status: ApplicationStatus = ApplicationStatus.draft


class ApplicationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ApplicationStatus | None = None
    notes: str | None = None
    applied_at: datetime | None = None


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    job_target_id: UUID
    resume_version_id: UUID
    status: ApplicationStatus
    applied_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ApplicationListItem(ApplicationRead):
    """An application row joined with job target, resume version, and kit context."""

    company: str | None
    title: str | None
    resume_version_label: str | None
    ats_score: float | None
    """After-tailoring headline score from the resume version's score_cache."""
    resume_pdf_ready: bool
    has_cover_letter: bool
    followup_count: int
    last_activity_at: datetime
