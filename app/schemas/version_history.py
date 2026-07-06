from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VersionJobTargetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    company: str | None = None
    title: str | None = None


class VersionDocumentAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pdf: bool = False
    docx: bool = False
    rendered_formats: list[str] = Field(default_factory=list)


class ResumeVersionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    label: str | None = None
    job_target: VersionJobTargetSummary | None = None
    template_id: str
    created_at: datetime
    headline_score: float | None = None
    document_availability: VersionDocumentAvailability


class DiffSummaryHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bullets_rewritten: int = 0
    bullets_unchanged: int = 0
    skills_reordered: bool = False
    requirements_targeted: list[str] = Field(default_factory=list)


class DiffChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    before: Any
    after: Any
    requirement_targeted: str | None = None


class ExperienceDiffGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experience_ref: str
    experience_index: int
    company: str | None = None
    title: str | None = None
    changes: list[DiffChange] = Field(default_factory=list)


class ProjectDiffGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_ref: str
    project_index: int
    name: str | None = None
    changes: list[DiffChange] = Field(default_factory=list)


class EnrichedVersionDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: UUID | None = None
    compare_from_version_id: UUID | None = None
    compare_to_version_id: UUID | None = None
    summary: DiffSummaryHeader
    experience_groups: list[ExperienceDiffGroup] = Field(default_factory=list)
    project_groups: list[ProjectDiffGroup] = Field(default_factory=list)
    section_reorderings: list[DiffChange] = Field(default_factory=list)
    other_changes: list[DiffChange] = Field(default_factory=list)
    discarded_rewrites: list[dict[str, Any]] = Field(default_factory=list)
    raw_diff: dict[str, Any] = Field(default_factory=dict)
