"""Integration tests for the bundle listing and detail API routes."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.models.bundle import PublishedBundle
from orchestrator.models.tower import PublishedTower, TowerCategory, TowerStatus

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_TOWER_HASH_A = "a" * 64
_TOWER_HASH_B = "b" * 64
_BUNDLE_ID_A = "1" * 64
_BUNDLE_ID_B = "2" * 64
_BUNDLE_ID_C = "3" * 64


def _make_tower(tower_hash: str) -> PublishedTower:
    """Create a :class:`PublishedTower` instance for FK satisfaction.

    Args:
        tower_hash: Unique hash for the tower.

    Returns:
        An unsaved :class:`PublishedTower` instance.
    """
    return PublishedTower(
        bundle_hash=tower_hash,
        category=TowerCategory.GAMING,
        status=TowerStatus.ACTIVE,
        total_price=1299.99,
        ml_id=None,
        component_skus={"cpu": "CPU-SKU-001", "ram": "RAM-SKU-002"},
    )


def _make_bundle(
    bundle_id: str,
    tower_hash: str,
    ml_id: str | None = None,
) -> PublishedBundle:
    """Create a :class:`PublishedBundle` instance for tests.

    Args:
        bundle_id: Unique bundle identifier.
        tower_hash: FK to the parent tower.
        ml_id: Optional ML system identifier.

    Returns:
        An unsaved :class:`PublishedBundle` instance.
    """
    return PublishedBundle(
        bundle_id=bundle_id,
        tower_hash=tower_hash,
        peripheral_skus={"keyboard": "KB-SKU-001", "mouse": "MS-SKU-002"},
        ml_id=ml_id,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/bundles/  — list endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_bundles_empty(api_client: httpx.AsyncClient) -> None:
    """GET /api/v1/bundles/ returns an empty list when no bundles exist."""
    response = await api_client.get("/api/v1/bundles/")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["bundles"] == []


@pytest.mark.asyncio
async def test_list_bundles_returns_data(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /api/v1/bundles/ returns the correct bundle summaries."""
    tower = _make_tower(_TOWER_HASH_A)
    db_session.add(tower)
    await db_session.flush()

    bundle_a = _make_bundle(_BUNDLE_ID_A, _TOWER_HASH_A)
    bundle_b = _make_bundle(_BUNDLE_ID_B, _TOWER_HASH_A, ml_id="ML-42")
    db_session.add_all([bundle_a, bundle_b])
    await db_session.commit()

    response = await api_client.get("/api/v1/bundles/")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    ids = {b["bundle_id"] for b in data["bundles"]}
    assert ids == {_BUNDLE_ID_A, _BUNDLE_ID_B}

    # Verify schema fields are present on the first returned item
    first = data["bundles"][0]
    assert "bundle_id" in first
    assert "tower_hash" in first
    assert "peripheral_skus" in first
    assert "ml_id" in first
    assert "created_at" in first


@pytest.mark.asyncio
async def test_list_bundles_pagination(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """skip/limit query params paginate the bundle list correctly."""
    tower = _make_tower(_TOWER_HASH_A)
    db_session.add(tower)
    await db_session.flush()

    bundle_a = _make_bundle(_BUNDLE_ID_A, _TOWER_HASH_A)
    bundle_b = _make_bundle(_BUNDLE_ID_B, _TOWER_HASH_A)
    bundle_c = _make_bundle(_BUNDLE_ID_C, _TOWER_HASH_A)
    db_session.add_all([bundle_a, bundle_b, bundle_c])
    await db_session.commit()

    # First page: skip=0, limit=2 → 2 results, count=3
    response = await api_client.get("/api/v1/bundles/", params={"skip": 0, "limit": 2})
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert len(data["bundles"]) == 2

    # Second page: skip=2, limit=2 → 1 result, count=3
    response = await api_client.get("/api/v1/bundles/", params={"skip": 2, "limit": 2})
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert len(data["bundles"]) == 1


# ---------------------------------------------------------------------------
# GET /api/v1/bundles/{bundle_id}/  — detail endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_bundle_by_id(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /api/v1/bundles/{id}/ returns full detail for an existing bundle."""
    tower = _make_tower(_TOWER_HASH_A)
    db_session.add(tower)
    await db_session.flush()

    bundle = _make_bundle(_BUNDLE_ID_A, _TOWER_HASH_A, ml_id="ML-99")
    db_session.add(bundle)
    await db_session.commit()
    await db_session.refresh(bundle)

    response = await api_client.get(f"/api/v1/bundles/{_BUNDLE_ID_A}/")

    assert response.status_code == 200
    data = response.json()
    assert data["bundle_id"] == _BUNDLE_ID_A
    assert data["tower_hash"] == _TOWER_HASH_A
    assert data["peripheral_skus"] == {"keyboard": "KB-SKU-001", "mouse": "MS-SKU-002"}
    assert data["ml_id"] == "ML-99"
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_get_bundle_not_found(api_client: httpx.AsyncClient) -> None:
    """GET /api/v1/bundles/{id}/ returns 404 for a non-existent bundle ID."""
    response = await api_client.get(f"/api/v1/bundles/{'z' * 64}/")

    assert response.status_code == 404
    assert response.json()["detail"] is not None
