from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.llm import LLMUsage

Tone = Literal["standard", "direct", "warm"]


class ProseClaimReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    violations: list[str] = Field(default_factory=list)
    proper_nouns_checked: list[str] = Field(default_factory=list)
    numbers_checked: list[str] = Field(default_factory=list)
    company_fact_sentences_checked: list[str] = Field(default_factory=list)


class ClaimUsed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    evidence_ref: str


class CoverLetterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body_markdown: str
    claims_used: list[ClaimUsed]


class CoverLetterResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    body_markdown: str
    word_count: int
    claim_report: ProseClaimReport
    usage: LLMUsage = Field(default_factory=LLMUsage)


class CoverLetterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume_version_id: UUID
    tone: Tone = "standard"


class CoverLetterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_target_id: UUID
    resume_version_id: UUID
    body_markdown: str
    tone: Tone
    word_count: int
    claim_report: dict
