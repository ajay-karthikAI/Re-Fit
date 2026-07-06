import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Upload(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An original resume file as uploaded, stored in S3."""

    __tablename__ = "uploads"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    s3_key: Mapped[str]
    filename: Mapped[str]
    source_format: Mapped[str]
