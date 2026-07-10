import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class AuthSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A bearer session issued at login/registration. Only the SHA-256 of the
    opaque token is stored, so a database leak does not leak usable sessions.
    A session is live while ``expires_at`` is in the future and ``revoked_at``
    is null; logout sets ``revoked_at``."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
