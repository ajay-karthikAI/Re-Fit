import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db import Base
from app.models.base import UUIDPrimaryKeyMixin


class CoverLetterTone(enum.StrEnum):
    standard = "standard"
    direct = "direct"
    warm = "warm"


class CoverLetter(UUIDPrimaryKeyMixin, Base):
    """Generated prose paired with a tailored resume version for a job target."""

    __tablename__ = "cover_letters"
    __table_args__ = (
        UniqueConstraint(
            "job_target_id",
            "resume_version_id",
            "tone",
            name="uq_cover_letters_job_target_id_resume_version_id_tone",
        ),
    )

    job_target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_targets.id"), index=True)
    resume_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resume_versions.id"), index=True
    )
    body_markdown: Mapped[str] = mapped_column(Text)
    tone: Mapped[CoverLetterTone] = mapped_column(Enum(CoverLetterTone, name="cover_letter_tone"))
    word_count: Mapped[int] = mapped_column(Integer)
    claim_report: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
