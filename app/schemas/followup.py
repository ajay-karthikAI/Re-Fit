from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.followup import FollowupKind
from app.schemas.cover_letter import ClaimUsed, ProseClaimReport
from app.schemas.llm import LLMUsage


class FollowupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: FollowupKind


class FollowupOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    body_markdown: str
    claims_used: list[ClaimUsed] = Field(default_factory=list)


class FollowupResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    application_id: UUID | None = None
    kind: FollowupKind
    subject: str
    body_markdown: str
    send_after: date | None
    word_count: int
    claim_report: ProseClaimReport
    usage: LLMUsage = Field(default_factory=LLMUsage)


class FollowupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    kind: FollowupKind
    subject: str
    body_markdown: str
    send_after: date | None
    created_at: datetime
