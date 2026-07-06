import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class ResumeVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tailored StructuredResume derived from a profile.

    ``job_target_id`` is null for manual/base versions; at most one version
    per (profile, job target) pair, enforced by a partial unique index.
    """

    __tablename__ = "resume_versions"
    __table_args__ = (
        Index(
            "uq_resume_versions_profile_job_target",
            "profile_id",
            "job_target_id",
            unique=True,
            postgresql_where=text("job_target_id IS NOT NULL AND deleted_at IS NULL"),
        ),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    job_target_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_targets.id"), index=True
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """Structured diff vs the base profile, for showing the user what changed."""
    score_cache: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    label: Mapped[str | None]
    template_id: Mapped[str] = mapped_column(default="classic", server_default="classic")
    template_variables: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
