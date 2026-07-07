import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Posting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One job posting ingested from a source board, deduplicated over time.

    The primary dedup key is ``(source_board_id, external_id)`` — the same
    posting re-fetched every run updates this row in place rather than creating
    a new one. ``content_hash`` (over title + description) drives change
    detection so an unchanged re-fetch is cheap and a changed one can re-trigger
    match scoring without a new row.

    Expiry is soft, never a delete: a posting that drops out of a fetch (or ages
    past the freshness window) is marked ``is_active=False`` so a user who
    already generated a kit for it keeps seeing it in their history.

    ``canonical_posting_id`` is a nullable self-FK used for *cross-board* dedup
    (the same role on a company's Greenhouse and syndicated to an RSS feed):
    duplicates are linked, never merged, so a wrongly-linked pair still leaves
    both real rows intact. A row with ``canonical_posting_id IS NULL`` is itself
    canonical; duplicates point at it and are hidden from the digest.
    """

    __tablename__ = "postings"
    __table_args__ = (
        UniqueConstraint("source_board_id", "external_id", name="uq_postings_board_external_id"),
    )

    source_board_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_boards.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    description_text: Mapped[str] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )
    content_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), index=True
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canonical_posting_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("postings.id", ondelete="SET NULL"), index=True
    )
    """NULL means this row is canonical; otherwise it points at the canonical row
    this posting duplicates on another board."""
    extracted_requirements: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """Cached JobRequirements (see app/schemas/jd.py) extracted from
    description_text by the one LLM call in app/services/jd.py. Shared across all
    saved searches so re-scoring never re-extracts; invalidated (set NULL) by the
    storage layer whenever content_hash changes."""
