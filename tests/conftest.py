import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

TEST_DB_NAME = "refit_test"


def _to_test_url(database_url: str) -> str:
    return database_url.rsplit("/", 1)[0] + f"/{TEST_DB_NAME}"


# Tests always run against the real refit_test Postgres database (see CLAUDE.md:
# never SQLite, never mock the database). Point the whole app at it before any
# app module builds an engine.
os.environ["DATABASE_URL"] = _to_test_url(get_settings().database_url)
get_settings.cache_clear()


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _create_schema() -> AsyncIterator[None]:
    """Build the schema in refit_test once per test session."""
    from app.db import Base
    import app.models  # noqa: F401  -- register all tables on Base.metadata

    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    yield


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    """Truncate all tables after each test so tests stay independent."""
    from app.db import Base

    yield
    engine = create_async_engine(get_settings().database_url)
    table_names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {table_names} CASCADE"))
    await engine.dispose()


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(get_settings().database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.db import dispose_engine
    from app.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    await dispose_engine()
