from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ScoreComponentName = Literal[
    "keyword_coverage",
    "section_integrity",
    "format_health",
    "length_and_density",
]
KeywordMatchType = Literal["text", "embedding", "none"]


class ScoreComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ScoreComponentName
    label: str
    score: float | None = None
    weight: float
    included: bool
    weighted_points: float | None = None
    notes: list[str] = Field(default_factory=list)


class TermCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str
    weight: float
    covered: bool
    match_type: KeywordMatchType
    text_match_score: float | None = None
    embedding_similarity: float | None = None


class KeywordCoverageBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float
    covered_terms: list[str] = Field(default_factory=list)
    missing_terms: list[str] = Field(default_factory=list)
    terms: list[TermCoverage] = Field(default_factory=list)


class SectionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    detail: str


class SectionIntegrityBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float
    checks: list[SectionCheck] = Field(default_factory=list)


class FormatHealthBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float | None = None
    renderer_available: bool = False
    match_rate: float | None = None
    matched_bullets: int | None = None
    total_bullets: int | None = None
    notes: list[str] = Field(default_factory=list)


class LengthDensityBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float
    estimated_pages: int
    word_count: int
    average_bullet_words: float
    recent_role_bullet_counts: list[int] = Field(default_factory=list)
    first_person_pronouns: int
    notes: list[str] = Field(default_factory=list)


class ATSScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline_score: float
    components: list[ScoreComponent]
    keyword_coverage: KeywordCoverageBreakdown
    section_integrity: SectionIntegrityBreakdown
    format_health: FormatHealthBreakdown
    length_and_density: LengthDensityBreakdown
