import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db import Base
from app.models.base import UUIDPrimaryKeyMixin


class FollowupKind(enum.StrEnum):
    post_apply = "post_apply"
    post_interview = "post_interview"
    checkin = "checkin"


class Followup(UUIDPrimaryKeyMixin, Base):
    """Copy-paste email artifact for an application."""

    __tablename__ = "followups"

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    kind: Mapped[FollowupKind] = mapped_column(Enum(FollowupKind, name="followup_kind"))
    subject: Mapped[str]
    body_markdown: Mapped[str] = mapped_column(Text)
    send_after: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
