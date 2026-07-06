from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.extract import ExtractedText, SourceFormat


class UploadResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: UUID
    filename: str
    s3_key: str
    source_format: SourceFormat
    created_at: datetime
    extracted: ExtractedText
