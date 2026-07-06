from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


RenderFormat = Literal["pdf", "docx"]


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: RenderFormat
    template: Literal["classic"] = "classic"
    font: str | None = None
    accent_color: str | None = None


class RenderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    kind: str
    s3_key: str
    download_url: str
    expires_in: int = 900
    page_count: int | None = None
    warnings: list[str] = Field(default_factory=list)
