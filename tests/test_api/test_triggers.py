"""Integration tests for the run trigger API endpoint."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.core.config import Settings, get_settings
from orchestrator.core.database import get_db_session
from orchestrator.main import app

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_KEY = "test-api-key-for-triggers"
_HASH_HOME = "h" * 64
_HASH_BUSINESS = "b" * 64
_HASH_GAMING = "g" * 64

_BUNDLE_HOME = "bh" * 32
_BUNDLE_BUSINESS = "bb" * 32
_BUNDLE_GAMING = "bg" * 32

# A minimal final state returned by the mocked workflow graph.
_SUCCESSFUL_STATE: dict[str, object] = {
    "completed_builds": [
        {"bundle_hash": _HASH_HOME, "tier": "Home", "total_price": 599.99},
        {"bundle_hash": _HASH_BUSINESS, "tier": "Business", "total_price": 899.99},
        {"bundle_hash": _HASH_GAMING, "tier": "Gaming", "total_price": 1499.99},
    ],
    "completed_bundles": [
        {"bundle_id": _BUNDLE_HOME, "tower_hash": _HASH_HOME, "tier": "Home"},
        {"bundle_id": _BUNDLE_BUSINESS, "tower_hash": _HASH_BUSINESS, "tier": "Business"},
        {"bundle_id": _BUNDLE_GAMING, "tower_hash": _HASH_GAMING, "tier": "Gaming"},
    ],
    "errors": [],
    "run_status": "completed",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def trigger_client(
    db_session: AsyncSession,
) -> AsyncGenerator[httpx.AsyncClient]:
    """Async HTTP test client with DB and settings overrides applied.

    Overrides ``get_db_session`` to use the in-memory SQLite session and
    ``get_settings`` to inject a known ``API_KEY``, so trigger tests can
    pass the correct ``X-API-Key`` header.

    Args:
        db_session: In-memory SQLite session from the shared conftest.

    Yields:
        An :class:`httpx.AsyncClient` wired to the FastAPI app.
    """

    async def override_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    def override_settings() -> Settings:
        return Settings(API_KEY=_VALID_KEY)

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_settings] = override_settings
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_settings, None)


# ---------------------------------------------------------------------------
# POST /api/v1/runs/trigger/
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_run_success(trigger_client: httpx.AsyncClient) -> None:
    """POST /trigger/ with valid key and all three tiers returns 200 with tower data."""
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = _SUCCESSFUL_STATE

    with patch("orchestrator.api.routes.triggers.build_assembly_graph", return_value=mock_graph):
        response = await trigger_client.post(
            "/api/v1/runs/trigger/",
            headers={"X-API-Key": _VALID_KEY},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["towers_created"] == 3
    assert set(data["tower_hashes"]) == {_HASH_HOME, _HASH_BUSINESS, _HASH_GAMING}
    assert data["bundles_created"] == 3
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_trigger_run_with_specific_tiers(trigger_client: httpx.AsyncClient) -> None:
    """POST /trigger/ with specific tiers invokes the workflow with only those tiers."""
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {
        "completed_builds": [
            {"bundle_hash": _HASH_HOME, "tier": "Home", "total_price": 599.99},
        ],
        "errors": [],
        "run_status": "completed",
    }

    with patch("orchestrator.api.routes.triggers.build_assembly_graph", return_value=mock_graph):
        response = await trigger_client.post(
            "/api/v1/runs/trigger/",
            headers={"X-API-Key": _VALID_KEY},
            json={"tiers": ["Home"]},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["towers_created"] == 1
    assert data["tower_hashes"] == [_HASH_HOME]

    # Verify the workflow was invoked with only the requested tier.
    mock_graph.ainvoke.assert_called_once_with({"requested_tiers": ["Home"]})


@pytest.mark.asyncio
async def test_trigger_run_no_api_key(trigger_client: httpx.AsyncClient) -> None:
    """POST /trigger/ without X-API-Key header returns 401 or 403."""
    response = await trigger_client.post("/api/v1/runs/trigger/")

    # FastAPI's APIKeyHeader raises 403 when the header is absent; accept
    # either 401 or 403 as both indicate an unauthenticated request.
    assert response.status_code in {401, 403}


@pytest.mark.asyncio
async def test_trigger_run_invalid_api_key(trigger_client: httpx.AsyncClient) -> None:
    """POST /trigger/ with wrong X-API-Key returns 401."""
    response = await trigger_client.post(
        "/api/v1/runs/trigger/",
        headers={"X-API-Key": "totally-wrong-key"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


@pytest.mark.asyncio
async def test_trigger_run_workflow_error(trigger_client: httpx.AsyncClient) -> None:
    """POST /trigger/ returns error details when the workflow fails for some tiers."""
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {
        "completed_builds": [],
        "errors": ["Tier 'Home': No CPU components available for tier 'Home'."],
        "run_status": "failed",
    }

    with patch("orchestrator.api.routes.triggers.build_assembly_graph", return_value=mock_graph):
        response = await trigger_client.post(
            "/api/v1/runs/trigger/",
            headers={"X-API-Key": _VALID_KEY},
            json={"tiers": ["Home"]},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["towers_created"] == 0
    assert data["tower_hashes"] == []
    assert data["bundles_created"] == 0
    assert len(data["errors"]) == 1
    assert "CPU" in data["errors"][0]


@pytest.mark.asyncio
async def test_trigger_run_default_tiers(trigger_client: httpx.AsyncClient) -> None:
    """POST /trigger/ with no body uses the default tiers (Home, Business, Gaming)."""
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = _SUCCESSFUL_STATE

    with patch("orchestrator.api.routes.triggers.build_assembly_graph", return_value=mock_graph):
        response = await trigger_client.post(
            "/api/v1/runs/trigger/",
            headers={"X-API-Key": _VALID_KEY},
        )

    assert response.status_code == 200
    # The workflow should have been invoked with all three default tiers.
    call_args = mock_graph.ainvoke.call_args[0][0]
    assert set(call_args["requested_tiers"]) == {"Home", "Business", "Gaming"}


@pytest.mark.asyncio
async def test_run_trigger_response_includes_bundles_created(
    trigger_client: httpx.AsyncClient,
) -> None:
    """RunTriggerResponse contains the bundles_created field populated from workflow state."""
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = _SUCCESSFUL_STATE

    with patch("orchestrator.api.routes.triggers.build_assembly_graph", return_value=mock_graph):
        response = await trigger_client.post(
            "/api/v1/runs/trigger/",
            headers={"X-API-Key": _VALID_KEY},
        )

    assert response.status_code == 200
    data = response.json()
    assert "bundles_created" in data
    assert data["bundles_created"] == 3


@pytest.mark.asyncio
async def test_run_trigger_response_bundles_created_default_zero(
    trigger_client: httpx.AsyncClient,
) -> None:
    """bundles_created defaults to 0 when no bundles are created by the workflow."""
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {
        "completed_builds": [
            {"bundle_hash": _HASH_HOME, "tier": "Home", "total_price": 599.99},
        ],
        "completed_bundles": [],
        "errors": [],
        "run_status": "completed",
    }

    with patch("orchestrator.api.routes.triggers.build_assembly_graph", return_value=mock_graph):
        response = await trigger_client.post(
            "/api/v1/runs/trigger/",
            headers={"X-API-Key": _VALID_KEY},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["bundles_created"] == 0


# ---------------------------------------------------------------------------
# New tests: assets_generated
# ---------------------------------------------------------------------------

_ASSET_HOME = {
    "bundle_id": _BUNDLE_HOME,
    "tier": "Home",
    "media_type": "image",
    "url": "http://img1",
}
_ASSET_BUSINESS = {
    "bundle_id": _BUNDLE_BUSINESS,
    "tier": "Business",
    "media_type": "image",
    "url": "http://img2",
}
_ASSET_GAMING = {
    "bundle_id": _BUNDLE_GAMING,
    "tier": "Gaming",
    "media_type": "video",
    "url": "http://vid1",
}

_FULL_PIPELINE_STATE: dict[str, object] = {
    **_SUCCESSFUL_STATE,
    "completed_assets": [_ASSET_HOME, _ASSET_BUSINESS, _ASSET_GAMING],
}


@pytest.mark.asyncio
async def test_trigger_response_includes_assets(
    trigger_client: httpx.AsyncClient,
) -> None:
    """RunTriggerResponse contains the assets_generated field populated from workflow state."""
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = _FULL_PIPELINE_STATE

    with patch("orchestrator.api.routes.triggers.build_assembly_graph", return_value=mock_graph):
        response = await trigger_client.post(
            "/api/v1/runs/trigger/",
            headers={"X-API-Key": _VALID_KEY},
        )

    assert response.status_code == 200
    data = response.json()
    assert "assets_generated" in data
    assert data["assets_generated"] == 3


@pytest.mark.asyncio
async def test_trigger_full_pipeline(
    trigger_client: httpx.AsyncClient,
) -> None:
    """Full pipeline state: builds + bundles + assets all reflected in response."""
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = _FULL_PIPELINE_STATE

    with patch("orchestrator.api.routes.triggers.build_assembly_graph", return_value=mock_graph):
        response = await trigger_client.post(
            "/api/v1/runs/trigger/",
            headers={"X-API-Key": _VALID_KEY},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["towers_created"] == 3
    assert data["bundles_created"] == 3
    assert data["assets_generated"] == 3
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_trigger_backward_compatible(
    trigger_client: httpx.AsyncClient,
) -> None:
    """Existing fields are unchanged when completed_assets is absent from workflow state."""
    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = _SUCCESSFUL_STATE  # no completed_assets key

    with patch("orchestrator.api.routes.triggers.build_assembly_graph", return_value=mock_graph):
        response = await trigger_client.post(
            "/api/v1/runs/trigger/",
            headers={"X-API-Key": _VALID_KEY},
        )

    assert response.status_code == 200
    data = response.json()
    # Legacy fields are intact
    assert data["status"] == "completed"
    assert data["towers_created"] == 3
    assert set(data["tower_hashes"]) == {_HASH_HOME, _HASH_BUSINESS, _HASH_GAMING}
    assert data["bundles_created"] == 3
    assert data["errors"] == []
    # New field defaults to zero when absent from state
    assert data["assets_generated"] == 0
