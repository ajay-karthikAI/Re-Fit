from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.short_answer import ShortAnswerKind
from app.schemas.cover_letter import ClaimUsed, ProseClaimReport
from app.schemas.llm import LLMUsage

QuestionKind = ShortAnswerKind


class ShortAnswerGenerationOutput(BaseModel):
    """LLM output shape: the answer plus the evidence each claim traces to."""

    model_config = ConfigDict(extra="forbid")

    body_markdown: str
    claims_used: list[ClaimUsed]


class ShortAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    question_kind: ShortAnswerKind | None = None
    """If omitted, inferred from the question text via the ATS keyword heuristic."""


class ShortAnswerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    question: str
    question_kind: ShortAnswerKind
    answer_markdown: str
    word_count: int
    claim_report: ProseClaimReport
    usage: LLMUsage = Field(default_factory=LLMUsage)


class ShortAnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_target_id: UUID
    question: str
    question_kind: ShortAnswerKind
    answer_markdown: str
    claim_report: dict
    created_at: datetime
