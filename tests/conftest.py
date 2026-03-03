"""Shared test fixtures."""

from collections.abc import AsyncGenerator

import httpx
import pytest

from orchestrator.main import app


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient]:
    """Yield an async HTTP test client wired to the FastAPI app."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client
