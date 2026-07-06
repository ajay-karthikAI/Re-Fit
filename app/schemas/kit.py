from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.cover_letter import Tone
from app.schemas.followup import FollowupRead
from app.schemas.llm import LLMUsage
from app.schemas.score import ATSScore
from app.services.templates import TemplateId


class KitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tone: Tone = "standard"
    template: TemplateId | None = None
    force: bool = False


class KitDiffSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: int = 0
    bullet_rewrites: int = 0
    skills_reordered: bool = False
    discarded_rewrites: int = 0
    rewrite_candidates: int = 0
    rewrites_accepted: int = 0
    rewrites_discarded: int = 0


class KitResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume_version_id: UUID
    score_before: ATSScore
    score_after: ATSScore
    resume_pdf_url: str
    cover_letter_id: UUID
    cover_letter_pdf_url: str
    diff_summary: KitDiffSummary
    usage: LLMUsage = Field(default_factory=LLMUsage)


class KitVersionDetail(BaseModel):
    """The resume version that went out with an application, for the kit view."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    label: str | None
    template_id: str
    created_at: datetime
    score_before: float | None
    score_after: float | None
    missing_terms: list[str] = Field(default_factory=list)
    pdf_url: str | None
    docx_url: str | None


class KitClaimSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    claims_checked: int
    violations: list[str] = Field(default_factory=list)


class KitCoverLetterDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tone: Tone
    body_markdown: str
    word_count: int
    claims: KitClaimSummary
    pdf_url: str | None


class ApplicationKitDetail(BaseModel):
    """Everything the tracker shows when a row expands: the exact kit that went out."""

    model_config = ConfigDict(extra="forbid")

    application_id: UUID
    resume_version: KitVersionDetail
    cover_letter: KitCoverLetterDetail | None
    followups: list[FollowupRead] = Field(default_factory=list)


class KitMissingPieces(BaseModel):
    model_config = ConfigDict(extra="forbid")

    missing_pieces: list[
        Literal[
            "canonical_profile",
            "requirements",
            "tailored_resume_version",
            "resume_pdf",
            "cover_letter",
            "cover_letter_pdf",
        ]
    ] = Field(default_factory=list)
