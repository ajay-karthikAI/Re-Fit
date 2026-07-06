import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class ApplicationStatus(enum.StrEnum):
    draft = "draft"
    applied = "applied"
    interview = "interview"
    rejected = "rejected"
    offer = "offer"


class Application(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tracks a submission: which exact resume version went to which job."""

    __tablename__ = "applications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_targets.id"), index=True)
    resume_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resume_versions.id"), index=True
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, name="application_status"),
        default=ApplicationStatus.draft,
        server_default="draft",
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
