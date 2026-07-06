import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

EMBEDDING_DIM = 384
"""all-MiniLM-L6-v2 output dimensionality."""


class BulletEmbedding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Embedding of one resume bullet, for JD-vs-resume similarity scoring."""

    __tablename__ = "bullet_embeddings"
    __table_args__ = (
        UniqueConstraint("resume_version_id", "bullet_ref"),
        Index(
            "ix_bullet_embeddings_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    resume_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="CASCADE"), index=True
    )
    bullet_ref: Mapped[str]
    """JSON-pointer-style path into StructuredResume, e.g. "experience/0/bullets/2"."""
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM))
