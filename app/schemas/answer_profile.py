from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.answer_profile import RelocationPreference, SalaryType, WorkAuthStatus


class AnswerProfileBase(BaseModel):
    """Fields shared by the write and read shapes, including the cross-field
    validation that matters here more than usual: these values get pasted
    straight into real job applications.
    """

    model_config = ConfigDict(extra="forbid")

    work_auth: WorkAuthStatus
    sponsorship_needed: bool
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = "USD"
    salary_type: SalaryType
    relocation: RelocationPreference
    notice_period_days: int | None = None
    pronouns: str | None = None
    referral_source_default: str | None = None
    eeo_prefs: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _salary_range_valid(self) -> "AnswerProfileBase":
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_max < self.salary_min
        ):
            raise ValueError(
                f"salary_max ({self.salary_max}) must be >= salary_min ({self.salary_min})"
            )
        return self

    @model_validator(mode="after")
    def _sponsorship_consistent_with_work_auth(self) -> "AnswerProfileBase":
        if self.work_auth == WorkAuthStatus.needs_sponsorship and not self.sponsorship_needed:
            raise ValueError(
                "sponsorship_needed must be true when work_auth is 'needs_sponsorship'"
            )
        return self


class AnswerProfileWrite(AnswerProfileBase):
    """PUT body: the whole form, resubmitted every time. No partial PATCH."""


class AnswerProfileRead(AnswerProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class AnswerProfileCompleteness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    complete: bool
    missing_fields: list[str]
