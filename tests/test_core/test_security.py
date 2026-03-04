"""Tests for the API key authentication dependency."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from orchestrator.core.config import Settings, get_settings
from orchestrator.core.security import verify_api_key

_VALID_KEY = "test-secret-key"


def _make_app(api_key: str) -> FastAPI:
    """Create a minimal FastAPI app with a protected route for testing.

    Args:
        api_key: The API key to configure in settings.

    Returns:
        A FastAPI instance with a single protected endpoint.
    """
    app = FastAPI()

    def override_settings() -> Settings:
        return Settings(API_KEY=api_key)

    app.dependency_overrides[get_settings] = override_settings

    @app.get("/protected")
    async def protected_route(key: str = Depends(verify_api_key)) -> dict[str, str]:
        """Return the validated key."""
        return {"key": key}

    return app


def test_verify_api_key_valid() -> None:
    """A correct X-API-Key header is accepted and the key is returned."""
    client = TestClient(_make_app(_VALID_KEY), raise_server_exceptions=True)
    response = client.get("/protected", headers={"X-API-Key": _VALID_KEY})
    assert response.status_code == 200
    assert response.json() == {"key": _VALID_KEY}


def test_verify_api_key_invalid() -> None:
    """An incorrect X-API-Key header returns HTTP 401."""
    client = TestClient(_make_app(_VALID_KEY), raise_server_exceptions=False)
    response = client.get("/protected", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


def test_verify_api_key_missing() -> None:
    """A missing X-API-Key header returns HTTP 401 or 403 (unauthenticated)."""
    client = TestClient(_make_app(_VALID_KEY), raise_server_exceptions=False)
    response = client.get("/protected")
    # APIKeyHeader with auto_error=True raises 403 when the header is absent;
    # accept either 401 or 403 as both indicate an unauthenticated request.
    assert response.status_code in {401, 403}


@pytest.mark.asyncio
async def test_verify_api_key_raises_401_on_invalid() -> None:
    """verify_api_key raises HTTPException with status 401 for a wrong key."""
    from fastapi import HTTPException

    settings = Settings(API_KEY=_VALID_KEY)

    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(api_key="bad-key", settings=settings)

    assert exc_info.value.status_code == 401
