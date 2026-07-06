import enum
import uuid

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class DocumentKind(enum.StrEnum):
    resume_pdf = "resume_pdf"
    resume_docx = "resume_docx"
    cover_letter_pdf = "cover_letter_pdf"
    cover_letter_docx = "cover_letter_docx"


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A rendered artifact stored in S3."""

    __tablename__ = "documents"

    resume_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[DocumentKind] = mapped_column(Enum(DocumentKind, name="document_kind"))
    s3_key: Mapped[str]
