"""Shared fixtures for integration tests.

Provides an async HTTP test client wired to an in-memory SQLite database
that is shared between the LangGraph node (which manages its own session via
``async_session_factory``) and the FastAPI route handlers (which use
``get_db_session``).

``StaticPool`` is used so that every SQLAlchemy connection resolves to the
same underlying aiosqlite connection, guaranteeing that rows committed by the
inventory-architect node are immediately visible to subsequent API requests.
"""

from collections.abc import AsyncGenerator
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# Import all models so Base.metadata discovers them before create_all.
import orchestrator.models  # noqa: F401
from orchestrator.core.config import Settings, get_settings
from orchestrator.core.database import get_db_session
from orchestrator.main import app
from orchestrator.models.base import Base

# API key injected into the overridden settings for every integration test.
INTEGRATION_API_KEY = "test-integration-api-key"


@pytest.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine]:
    """Yield a shared in-memory SQLite engine with all ORM tables created.

    Uses ``StaticPool`` so that every connection (whether from the LangGraph
    node or from the FastAPI test client) touches the same in-memory database.
    This allows data committed by the node to be immediately readable by
    subsequent API route handlers in the same test.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def integration_client(sqlite_engine: AsyncEngine) -> AsyncGenerator[httpx.AsyncClient]:
    """Yield an async HTTP client with the full assembly pipeline wired together.

    Three overrides are applied so the entire pipeline runs against an
    isolated in-memory SQLite database:

    1. ``get_db_session`` FastAPI dependency → yields sessions from the test
       engine, so tower-listing and detail routes read from the same DB.
    2. ``get_settings`` FastAPI dependency → returns a ``Settings`` instance
       with a known ``API_KEY`` so trigger tests can include the correct header.
    3. ``async_session_factory`` inside the inventory-architect node → replaced
       with the test session factory so the node persists towers to the same
       in-memory SQLite that the API routes query.

    Args:
        sqlite_engine: Shared in-memory SQLite engine from the sibling fixture.

    Yields:
        An :class:`httpx.AsyncClient` wired to the FastAPI app.
    """
    test_session_factory = async_sessionmaker(
        sqlite_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db_session() -> AsyncGenerator[AsyncSession]:
        async with test_session_factory() as session:
            yield session

    def override_settings() -> Settings:
        return Settings(API_KEY=INTEGRATION_API_KEY)

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_settings] = override_settings

    try:
        with patch(
            "orchestrator.graph.nodes.inventory_architect.async_session_factory",
            test_session_factory,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_settings, None)
