from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SearchFilters(BaseModel):
    """Simple, optional post-filters over matched postings. Not a query DSL."""

    model_config = ConfigDict(extra="forbid")

    locations: list[str] | None = None
    departments: list[str] | None = None


class SavedSearchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    name: str = Field(min_length=1)
    profile_id: UUID
    min_score: float = Field(default=75.0, ge=0.0, le=100.0)
    filters: SearchFilters | None = None


class SavedSearchUpdate(BaseModel):
    """PATCH: toggle activation or move the score bar. Both optional."""

    model_config = ConfigDict(extra="forbid")

    is_active: bool | None = None
    min_score: float | None = Field(default=None, ge=0.0, le=100.0)


class SavedSearchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    profile_id: UUID
    min_score: float
    filters: SearchFilters | None
    is_active: bool
    created_at: datetime


class MatchResult(BaseModel):
    """Score of one posting against one saved search's profile."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=100.0)
    missing_terms: list[str]


class PostingMatchRead(BaseModel):
    """A scored posting for the matches view, richest fields inlined for the UI."""

    model_config = ConfigDict(extra="forbid")

    posting_id: UUID
    title: str
    company_name: str
    location: str | None
    department: str | None
    url: str
    posted_at: datetime | None
    score: float
    missing_terms: list[str]
    computed_at: datetime


class Digest(BaseModel):
    """A built digest of matches new to the user for one saved search."""

    model_config = ConfigDict(extra="forbid")

    saved_search_id: UUID
    count: int
    new_matches: list[PostingMatchRead]
    top_3_preview: list[PostingMatchRead]


class DigestRead(BaseModel):
    """A persisted digest row (generation only; delivery is a separate concern)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    saved_search_id: UUID
    new_match_count: int
    posting_ids: list[UUID]
    created_at: datetime
