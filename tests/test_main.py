"""Integration tests for the FastAPI application."""

import httpx
import pytest


@pytest.mark.asyncio
async def test_health_endpoint(async_client: httpx.AsyncClient) -> None:
    """GET /health returns 200 with status ok."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_app_has_cors_headers(async_client: httpx.AsyncClient) -> None:
    """Verify CORS middleware is active."""
    response = await async_client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
