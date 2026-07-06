from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceFormat = Literal["pdf", "docx"]


class ExtractedText(BaseModel):
    """Deterministic raw-text extraction from an uploaded resume file.

    This is pre-processing only — LLM normalization into StructuredResume
    happens downstream. ``raw_text`` preserves bullet glyphs (•, -, *) because
    they are structure signals for the LLM parser.
    """

    model_config = ConfigDict(extra="forbid")

    raw_text: str
    page_count: int | None
    source_format: SourceFormat
    extraction_warnings: list[str] = Field(default_factory=list)
