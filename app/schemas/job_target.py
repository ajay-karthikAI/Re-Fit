from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobTargetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_description: str = Field(min_length=1)
    company: str | None = None
    title: str | None = None
    source_url: str | None = None


class JobTargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    company: str | None
    title: str | None
    source_url: str | None
    raw_description: str
    extracted_requirements: dict[str, Any] | None
    created_at: datetime
