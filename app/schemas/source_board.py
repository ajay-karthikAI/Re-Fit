from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.source_board import BoardHealth, SourceKind


class SourceBoardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: SourceKind
    identifier: str = Field(min_length=1)
    """Board token (Greenhouse), site (Lever), or feed URL (RSS)."""
    company_name: str = Field(min_length=1)
    user_id: UUID | None = None
    """Owner of this board; NULL registers a system/seed board watched for everyone."""


class SourceBoardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None
    source: SourceKind
    identifier: str
    company_name: str
    health: BoardHealth
    consecutive_failures: int
    needs_attention: bool
    """True when the board is degraded/dead or has any failure streak — the
    at-a-glance signal that a board is silently dying."""
    last_checked_at: datetime | None
    last_success_at: datetime | None
    created_at: datetime
