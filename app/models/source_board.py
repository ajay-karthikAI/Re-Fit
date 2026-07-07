import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class SourceKind(enum.StrEnum):
    greenhouse = "greenhouse"
    lever = "lever"
    rss = "rss"


class BoardHealth(enum.StrEnum):
    healthy = "healthy"
    degraded = "degraded"
    dead = "dead"


class SourceBoard(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A board/feed we watch for postings on behalf of a user (or everyone).

    ``identifier`` is source-dependent: a Greenhouse board token, a Lever site,
    or an RSS/Atom feed URL. A ``user_id`` of NULL marks a system/seed board
    watched for every user. Health degrades as consecutive fetch failures pile
    up so ingestion stops hammering dead boards without ever failing silently
    (see ``app/services/sources/registry.py``).
    """

    __tablename__ = "source_boards"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source: Mapped[SourceKind] = mapped_column(Enum(SourceKind, name="source_kind"))
    identifier: Mapped[str] = mapped_column(String)
    """Board token (Greenhouse), site (Lever), or feed URL (RSS)."""
    company_name: Mapped[str] = mapped_column(String)
    health: Mapped[BoardHealth] = mapped_column(
        Enum(BoardHealth, name="board_health"),
        default=BoardHealth.healthy,
        server_default=BoardHealth.healthy.value,
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def needs_attention(self) -> bool:
        """True the moment a board is anything but cleanly healthy — the single
        glance that tells you a board is silently dying or dead."""
        return self.health is not BoardHealth.healthy or self.consecutive_failures > 0
