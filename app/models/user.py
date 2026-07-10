from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A workspace account. ``password_hash`` is nullable because accounts
    created before password auth (dev-picker/seed users) carry no credential;
    they cannot log in until they claim a password via /auth/register."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(default=None)
