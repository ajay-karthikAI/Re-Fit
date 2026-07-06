"""The ApplyKit: one screen-ready payload that composes everything a user needs
to fill an application form in under three minutes — resolved field values,
ready-to-attach documents, the gaps only they can fill, and a checklist ordered
to match the real form's physical flow.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.application import ApplicationStatus
from app.schemas.ats_fields import FieldPlanItem, FieldStatus

ChecklistAction = Literal["copy", "upload", "select", "submit"]
"""What the user physically does for a step: one-click copy, file upload,
dropdown select, or the final submit."""


class ApplyKitDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    download_url: str | None
    ready: bool


class AnswerProfileGap(BaseModel):
    """A required answer-profile fact the form needs but the user hasn't provided."""

    model_config = ConfigDict(extra="forbid")

    field: str
    label: str
    link_target: str
    """Frontend route to the answer-profile form with this field pre-focused."""


class ChecklistStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int
    section: str
    field_key: str | None
    """The FieldSpec key this step drives, or ``None`` for the terminal submit step."""
    label: str
    action: ChecklistAction
    status: FieldStatus


class ApplyKit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_target_id: UUID
    source_ats: str
    source_url: str | None
    field_plan: list[FieldPlanItem]
    documents: list[ApplyKitDocument]
    answer_profile_gaps: list[AnswerProfileGap]
    checklist: list[ChecklistStep]


class ApplyKitRegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_key: str


class TrackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ApplicationStatus = ApplicationStatus.applied
