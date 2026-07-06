import enum
import hashlib
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db import Base
from app.models.base import UUIDPrimaryKeyMixin


class ShortAnswerKind(enum.StrEnum):
    why_company = "why_company"
    why_role = "why_role"
    custom = "custom"


def hash_question(question: str) -> str:
    """Normalize whitespace/case and hash, so cosmetic re-phrasings of the
    same ATS field still collide on the (job_target_id, question) uniqueness.
    """
    normalized = re.sub(r"\s+", " ", question).strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


class ShortAnswer(UUIDPrimaryKeyMixin, Base):
    """A generated response to an ATS short-answer form field for one job
    target, e.g. "why this company" or "why this role".
    """

    __tablename__ = "short_answers"
    __table_args__ = (
        UniqueConstraint(
            "job_target_id",
            "question_hash",
            name="uq_short_answers_job_target_id_question_hash",
        ),
    )

    job_target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_targets.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    question_hash: Mapped[str] = mapped_column(String(length=64))
    answer_markdown: Mapped[str] = mapped_column(Text)
    question_kind: Mapped[ShortAnswerKind] = mapped_column(
        Enum(ShortAnswerKind, name="short_answer_kind")
    )
    claim_report: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
