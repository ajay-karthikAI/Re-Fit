import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BulletEmbedding, Profile, ResumeVersion, User
from app.models.bullet_embedding import EMBEDDING_DIM
from app.services.embeddings import embed_texts, populate_embeddings

RESUME_DATA = {
    "contact": {"full_name": "Embed Test", "email": "embed@example.com"},
    "summary": None,
    "experience": [
        {
            "company": "Acme",
            "title": "Engineer",
            "start_date": "2020-01",
            "end_date": None,
            "bullets": [
                "built REST APIs in FastAPI",
                "led migration to Kubernetes",
            ],
            "technologies": [],
        }
    ],
    "education": [],
    "skills": [],
    "projects": [
        {
            "name": "sidecar",
            "description": None,
            "bullets": ["wrote a CLI in Go"],
            "technologies": [],
            "url": None,
        }
    ],
    "schema_version": "1.0",
}


def test_embeddings_shape_and_normalization() -> None:
    vectors = embed_texts(["hello world"])
    assert vectors.shape == (1, EMBEDDING_DIM)
    assert vectors.dtype == np.float32
    assert abs(float(np.linalg.norm(vectors[0])) - 1.0) < 1e-5


def test_semantically_similar_bullets_score_higher() -> None:
    vectors = embed_texts(
        [
            "built REST APIs in FastAPI",
            "developed FastAPI endpoints",
            "the cat sat on the windowsill",
        ]
    )
    similar = float(vectors[0] @ vectors[1])
    unrelated = float(vectors[0] @ vectors[2])
    assert similar > unrelated, (similar, unrelated)


def test_embed_texts_is_deterministic_and_cached() -> None:
    first = embed_texts(["determinism check"])
    second = embed_texts(["determinism check"])
    assert np.array_equal(first, second)


async def test_vectors_round_trip_through_postgres(session: AsyncSession) -> None:
    user = User(email="embed-roundtrip@example.com")
    session.add(user)
    await session.flush()
    profile = Profile(user_id=user.id, data=RESUME_DATA, is_canonical=True)
    session.add(profile)
    await session.flush()
    version = ResumeVersion(profile_id=profile.id, data=RESUME_DATA)
    session.add(version)
    await session.commit()

    count = await populate_embeddings(session, version.id)
    assert count == 3  # 2 experience bullets + 1 project bullet

    rows = (
        (
            await session.execute(
                select(BulletEmbedding)
                .where(BulletEmbedding.resume_version_id == version.id)
                .order_by(BulletEmbedding.bullet_ref)
            )
        )
        .scalars()
        .all()
    )
    assert [r.bullet_ref for r in rows] == [
        "experience/0/bullets/0",
        "experience/0/bullets/1",
        "projects/0/bullets/0",
    ]
    for row in rows:
        stored = np.asarray(row.embedding, dtype=np.float32)
        assert stored.shape == (EMBEDDING_DIM,)
        recomputed = embed_texts([row.text])[0]
        assert np.allclose(stored, recomputed, atol=1e-6)

    # Idempotent: repopulating replaces rather than duplicates.
    assert await populate_embeddings(session, version.id) == 3
    total = (
        (
            await session.execute(
                select(BulletEmbedding).where(BulletEmbedding.resume_version_id == version.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(total) == 3
