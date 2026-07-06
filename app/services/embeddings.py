"""Deterministic embedding layer: local sentence-transformers, no API calls.

Model all-MiniLM-L6-v2 (384 dims), embeddings L2-normalized so cosine
similarity is a plain dot product. Results are cached in-process (LRU keyed
on text hash) and persisted per resume version in the pgvector-backed
bullet_embeddings table.
"""

import hashlib
import logging
import uuid
from collections import OrderedDict
from functools import lru_cache
from typing import TYPE_CHECKING

import anyio.to_thread
import numpy as np
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BulletEmbedding, ResumeVersion
from app.models.bullet_embedding import EMBEDDING_DIM
from app.schemas.resume import StructuredResume
from app.services.errors import NotFoundError

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"
_CACHE_MAX_ENTRIES = 8192

_cache: OrderedDict[str, np.ndarray] = OrderedDict()


@lru_cache(maxsize=1)
def _model() -> "SentenceTransformer":
    # Deferred import: sentence_transformers pulls in torch, which is slow to
    # import and unnecessary for code paths that never embed.
    from sentence_transformers import SentenceTransformer

    logger.info("loading embedding model %s", MODEL_NAME)
    return SentenceTransformer(MODEL_NAME)


def _key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed texts into a (len(texts), 384) float32 array of unit vectors.

    Cached per text; only cache misses hit the model, in one batch.
    """
    keys = [_key(t) for t in texts]

    missing: dict[str, str] = {}  # key -> text, deduplicated, insertion-ordered
    for key, text in zip(keys, texts, strict=True):
        if key not in _cache and key not in missing:
            missing[key] = text

    if missing:
        vectors = _model().encode(list(missing.values()), normalize_embeddings=True)
        for key, vector in zip(missing.keys(), vectors, strict=True):
            _cache[key] = np.asarray(vector, dtype=np.float32)
        while len(_cache) > _CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)

    rows = []
    for key in keys:
        _cache.move_to_end(key)
        rows.append(_cache[key])
    return np.stack(rows) if rows else np.empty((0, EMBEDDING_DIM), dtype=np.float32)


def _bullet_refs(resume: StructuredResume) -> list[tuple[str, str]]:
    """All (json-pointer-ref, bullet text) pairs in a resume."""
    refs: list[tuple[str, str]] = []
    for i, item in enumerate(resume.experience):
        for j, bullet in enumerate(item.bullets):
            refs.append((f"experience/{i}/bullets/{j}", bullet))
    for i, project in enumerate(resume.projects):
        for j, bullet in enumerate(project.bullets):
            refs.append((f"projects/{i}/bullets/{j}", bullet))
    return refs


async def populate_embeddings(session: AsyncSession, resume_version_id: uuid.UUID) -> int:
    """Compute and store embeddings for every bullet in a resume version.

    Idempotent: existing rows for the version are replaced. Returns the number
    of bullets embedded.
    """
    version = await session.get(ResumeVersion, resume_version_id)
    if version is None:
        raise NotFoundError(f"resume version {resume_version_id} not found")

    resume = StructuredResume.model_validate(version.data)
    refs = _bullet_refs(resume)
    vectors = await anyio.to_thread.run_sync(embed_texts, [text for _, text in refs])

    await session.execute(
        delete(BulletEmbedding).where(BulletEmbedding.resume_version_id == resume_version_id)
    )
    session.add_all(
        BulletEmbedding(
            resume_version_id=resume_version_id,
            bullet_ref=ref,
            text=text,
            embedding=vector,
        )
        for (ref, text), vector in zip(refs, vectors, strict=True)
    )
    await session.commit()
    logger.info("stored %d bullet embeddings for version %s", len(refs), resume_version_id)
    return len(refs)
