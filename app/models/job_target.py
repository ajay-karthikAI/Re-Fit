import uuid
from typing import Any

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class JobTarget(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A job posting the user wants to tailor a resume for."""

    __tablename__ = "job_targets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    company: Mapped[str | None]
    title: Mapped[str | None]
    source_url: Mapped[str | None]
    raw_description: Mapped[str] = mapped_column(Text)
    extracted_requirements: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """Filled in later by the LLM requirement-extraction step."""
