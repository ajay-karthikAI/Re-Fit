"""Canonical structured resume format.

This schema is the shared contract between the LLM parser, the tailoring
engine, and the renderers. Every field must originate from the user's source
material — per the product invariant in CLAUDE.md, nothing here may ever be
fabricated by the pipeline.

All models forbid unknown fields so that malformed LLM output fails loudly at
the validation boundary instead of leaking into downstream stages.

Dates are strings in ``YYYY-MM`` form (resumes don't carry day precision);
``None`` in ``end_date`` means "present".
"""

import re
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    StringConstraints,
    model_validator,
)

_YEAR_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _validate_year_month(value: str) -> str:
    if not _YEAR_MONTH_RE.fullmatch(value):
        raise ValueError(f"date must be in YYYY-MM format with a valid month, got {value!r}")
    return value


YearMonth = Annotated[str, AfterValidator(_validate_year_month)]
"""A month-precision date, e.g. ``"2023-07"``. Lexicographic order == chronological order."""

Bullet = Annotated[str, StringConstraints(min_length=1, max_length=300)]
"""A single resume bullet point: non-empty, capped so renderers can rely on line budgets."""


class ContactInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str
    email: EmailStr
    phone: str | None = None
    location: str | None = None
    linkedin_url: HttpUrl | None = None
    github_url: HttpUrl | None = None
    portfolio_url: HttpUrl | None = None


class ExperienceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str
    title: str
    location: str | None = None
    start_date: YearMonth
    end_date: YearMonth | None = None
    """``None`` means the role is current ("present")."""
    bullets: list[Bullet] = Field(min_length=1)
    technologies: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _end_not_before_start(self) -> "ExperienceItem":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError(
                f"end_date {self.end_date!r} must not be before start_date {self.start_date!r}"
            )
        return self


class EducationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: str
    degree: str
    field: str | None = None
    graduation_date: YearMonth | None = None
    details: list[str] = Field(default_factory=list)


class ProjectItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    bullets: list[Bullet] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    url: HttpUrl | None = None


class SkillGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    """Display heading for the group, e.g. ``"Languages"`` or ``"Cloud"``."""
    items: list[str] = Field(min_length=1)


class StructuredResume(BaseModel):
    """The complete parsed resume.

    Section lists may be empty (not every resume has projects), but items
    inside them are strictly validated. ``schema_version`` is pinned so stored
    resumes can be migrated if the contract ever changes.
    """

    model_config = ConfigDict(extra="forbid")

    contact: ContactInfo
    summary: str | None = Field(default=None, max_length=600)
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    skills: list[SkillGroup] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    schema_version: Literal["1.0"] = "1.0"
