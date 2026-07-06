from pydantic import BaseModel, ConfigDict, Field

from app.schemas.llm import LLMUsage
from app.schemas.resume import StructuredResume


class LLMContactInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str
    email: str
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None


class LLMExperienceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str
    title: str
    location: str | None = None
    start_date: str
    end_date: str | None = None
    bullets: list[str] = Field(min_length=1)
    technologies: list[str] = Field(default_factory=list)


class LLMEducationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: str
    degree: str
    field: str | None = None
    graduation_date: str | None = None
    details: list[str] = Field(default_factory=list)


class LLMProjectItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    url: str | None = None


class LLMSkillGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    items: list[str] = Field(min_length=1)


class LLMStructuredResume(BaseModel):
    """Loose mirror of StructuredResume for the LLM wire format.

    Strict validation (YYYY-MM date regex, email/URL formats, bullet length
    limits) happens in Python after the call, via StructuredResume.model_validate.
    Putting those constraints directly in the JSON schema handed to the model
    makes Anthropic's structured-output grammar too large to compile
    ("The compiled grammar is too large" 400).
    """

    model_config = ConfigDict(extra="forbid")

    contact: LLMContactInfo
    summary: str | None = None
    experience: list[LLMExperienceItem] = Field(default_factory=list)
    education: list[LLMEducationItem] = Field(default_factory=list)
    skills: list[LLMSkillGroup] = Field(default_factory=list)
    projects: list[LLMProjectItem] = Field(default_factory=list)


class ResumeParseOutput(BaseModel):
    """The LLM's structured-output schema for the parse call."""

    model_config = ConfigDict(extra="forbid")

    resume: LLMStructuredResume
    confidence_notes: list[str] = Field(default_factory=list)
    """Decisions the model was unsure about (ambiguous sections, date formats,
    where an unrecognized section was folded in, ...)."""


class ParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resume: StructuredResume
    confidence_notes: list[str]
    """Model uncertainty notes plus deterministic faithfulness-check warnings."""
    usage: LLMUsage
