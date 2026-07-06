from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.llm import LLMUsage
from app.schemas.resume import StructuredResume
from app.schemas.score import ATSScore


class TailorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_target_id: UUID


class TailorDiffEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bullet_ref: str
    before: Any
    after: Any
    requirement_targeted: str | None = None


class DiscardedRewrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bullet_ref: str
    before: str
    proposed: str
    reasons: list[str] = Field(default_factory=list)
    requirement_targeted: str | None = None


class TailorStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bullets_scored: int = 0
    rewrite_candidates: int = 0
    experience_items_rewritten: int = 0
    rewrites_requested: int = 0
    rewrites_returned: int = 0
    rewrites_accepted: int = 0
    rewrites_discarded: int = 0
    skills_reordered: bool = False
    relevance_threshold: float
    max_rewrites: int
    usage: LLMUsage = Field(default_factory=LLMUsage)


class TailorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: UUID | None = None
    resume: StructuredResume
    diff: list[TailorDiffEntry] = Field(default_factory=list)
    stats: TailorStats
    discarded_rewrites: list[DiscardedRewrite] = Field(default_factory=list)
    score_before: ATSScore | None = None
    score_after: ATSScore | None = None


class BulletRewrite(BaseModel):
    """One model-proposed rewrite for a candidate bullet."""

    model_config = ConfigDict(extra="forbid")

    bullet_ref: str
    original: str
    rewritten: str
    requirement_targeted: str | None = None
    claims_preserved: bool


class ExperienceRewriteOutput(BaseModel):
    """Structured LLM output for one experience item."""

    model_config = ConfigDict(extra="forbid")

    rewrites: list[BulletRewrite]
