import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Profile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user's source resume as a StructuredResume dump (see app/schemas/resume.py).

    Exactly one canonical profile per user, enforced by a partial unique index.
    """

    __tablename__ = "profiles"
    __table_args__ = (
        Index(
            "uq_profiles_one_canonical_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_canonical"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_canonical: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
