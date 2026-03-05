"""Shared fixtures for API integration tests.

Provides an async HTTP test client with the database session overridden
to use an in-memory SQLite database, keeping tests hermetic and fast.
"""

from collections.abc import AsyncGenerator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.core.database import get_db_session
from orchestrator.main import app


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
