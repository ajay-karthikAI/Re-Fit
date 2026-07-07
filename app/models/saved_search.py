import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class SavedSearch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A standing query that scores ingested postings against one of the user's
    resume profiles. A user can keep several (e.g. "AI/ML roles" vs "healthcare
    AI roles") against different profiles, each with its own score bar."""

    __tablename__ = "saved_searches"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    """Which resume this search matches postings against."""
    min_score: Mapped[float] = mapped_column(Float, default=75.0, server_default=text("75.0"))
    filters: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """Optional, simple post-filters, e.g. {"locations": [...], "departments": [...]}.
    Deliberately not a query DSL."""
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"), index=True)
    last_digest_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """When the last digest was generated, so "new matches" means new to the user
    (not the same jobs every day). NULL until the first digest."""


class PostingMatch(UUIDPrimaryKeyMixin, Base):
    """A cached score of one posting against one saved search.

    Recomputed only when the inputs change: the posting's ``content_hash`` (its
    text) or the saved search's ``profile_id`` (the resume). Those identities are
    stored here so the expensive path — one LLM extraction per new/changed
    posting — is skipped when nothing changed."""

    __tablename__ = "posting_matches"
    __table_args__ = (
        UniqueConstraint("posting_id", "saved_search_id", name="uq_posting_matches_posting_search"),
    )

    posting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("postings.id", ondelete="CASCADE"), index=True
    )
    saved_search_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("saved_searches.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[float] = mapped_column(Float)
    missing_terms: Mapped[list[str]] = mapped_column(JSONB)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    scored_content_hash: Mapped[str] = mapped_column(Text)
    """posting.content_hash this score was computed against — the change key."""
    scored_profile_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    """saved_search.profile_id this score was computed against — the other key."""


class Digest(UUIDPrimaryKeyMixin, Base):
    """A generated digest of new matches for one saved search.

    Deliberately generation-only: this row is the *content* of a digest, decoupled
    from *delivery* (email/push/in-app), which is a separate concern so channels
    can be swapped without touching digest logic (see CLAUDE.md)."""

    __tablename__ = "digests"

    saved_search_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("saved_searches.id", ondelete="CASCADE"), index=True
    )
    new_match_count: Mapped[int] = mapped_column()
    posting_ids: Mapped[list[str]] = mapped_column(JSONB)
    """Posting UUIDs (as strings) included in this digest, newest-scored first."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
