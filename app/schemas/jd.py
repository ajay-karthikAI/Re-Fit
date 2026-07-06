from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.llm import LLMUsage

Seniority = Literal["intern", "junior", "mid", "senior", "staff", "lead", "unknown"]


class RequirementItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str
    weight: float = Field(ge=0.0, le=1.0)
    """Importance inferred from emphasis and repetition in the JD."""
    evidence: str
    """Short verbatim snippet from the JD supporting this requirement (for UI)."""


class JobRequirements(BaseModel):
    """Structured requirements extracted from a raw job description."""

    model_config = ConfigDict(extra="forbid")

    hard_skills: list[RequirementItem]
    soft_skills: list[RequirementItem]
    domain_terms: list[str]
    seniority: Seniority
    must_haves: list[str]
    """Requirements the JD marks as explicitly required."""
    nice_to_haves: list[str]


class JDExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: JobRequirements
    usage: LLMUsage
