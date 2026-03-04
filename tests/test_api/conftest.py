"""Shared fixtures for API integration tests.

Provides an async HTTP test client with the database session overridden
to use an in-memory SQLite database, keeping tests hermetic and fast.
"""

from collections.abc import AsyncGenerator

import httpx
import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Import all models so Base.metadata discovers them before create_all.
import orchestrator.models  # noqa: F401
from orchestrator.core.database import get_db_session
from orchestrator.main import app
from orchestrator.models.base import Base


@pytest.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine]:
    """Yield an in-memory SQLite async engine with all ORM tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(sqlite_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """Yield an async DB session bound to the in-memory SQLite engine."""
    factory = async_sessionmaker(sqlite_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def api_client(db_session: AsyncSession) -> AsyncGenerator[httpx.AsyncClient]:
    """Yield an async HTTP test client with the DB session overridden.

    Overrides the ``get_db_session`` FastAPI dependency so all route handlers
    use the in-memory SQLite session instead of the production database.

    Args:
        db_session: In-memory async DB session fixture.

    Yields:
        An :class:`httpx.AsyncClient` wired to the FastAPI app.
    """

    async def override_get_db_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
