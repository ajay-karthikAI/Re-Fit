from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Auth is a stub for now — no password handling yet."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(unique=True, index=True)
