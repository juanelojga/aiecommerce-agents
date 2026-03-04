"""Integration tests for the tower listing and detail API routes."""

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.models.tower import PublishedTower, TowerCategory, TowerStatus

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64
_NOW = datetime(2025, 6, 1, 10, 0, 0, tzinfo=UTC)


def _make_tower(
    bundle_hash: str,
    category: TowerCategory = TowerCategory.GAMING,
    status: TowerStatus = TowerStatus.ACTIVE,
    total_price: float = 1299.99,
    ml_id: str | None = None,
) -> PublishedTower:
    """Helper to create a :class:`PublishedTower` instance for tests.

    Args:
        bundle_hash: Unique hash for the tower.
        category: Tower category enum value.
        status: Tower status enum value.
        total_price: Total price of the build.
        ml_id: Optional ML system identifier.

    Returns:
        An unsaved :class:`PublishedTower` instance.
    """
    return PublishedTower(
        bundle_hash=bundle_hash,
        category=category,
        status=status,
        total_price=total_price,
        ml_id=ml_id,
        component_skus={"cpu": "CPU-SKU-001", "ram": "RAM-SKU-002"},
    )


# ---------------------------------------------------------------------------
# GET /api/v1/towers/  — list endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_towers_empty(api_client: httpx.AsyncClient) -> None:
    """GET /api/v1/towers/ returns an empty list when no towers exist."""
    response = await api_client.get("/api/v1/towers/")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["towers"] == []


@pytest.mark.asyncio
async def test_list_towers_with_data(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /api/v1/towers/ returns the correct tower summaries."""
    tower_a = _make_tower(_HASH_A, category=TowerCategory.HOME, total_price=599.99)
    tower_b = _make_tower(_HASH_B, category=TowerCategory.GAMING, total_price=1499.00)
    db_session.add_all([tower_a, tower_b])
    await db_session.commit()

    response = await api_client.get("/api/v1/towers/")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    hashes = {t["bundle_hash"] for t in data["towers"]}
    assert hashes == {_HASH_A, _HASH_B}

    # Verify schema fields are present on the first returned item
    first = data["towers"][0]
    assert "bundle_hash" in first
    assert "category" in first
    assert "status" in first
    assert "ml_id" in first
    assert "total_price" in first
    assert "created_at" in first


@pytest.mark.asyncio
async def test_list_towers_filter_category(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /api/v1/towers/?category=Gaming returns only Gaming towers."""
    db_session.add(_make_tower(_HASH_A, category=TowerCategory.HOME))
    db_session.add(_make_tower(_HASH_B, category=TowerCategory.GAMING))
    db_session.add(_make_tower(_HASH_C, category=TowerCategory.GAMING))
    await db_session.commit()

    response = await api_client.get("/api/v1/towers/", params={"category": "Gaming"})

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    for tower in data["towers"]:
        assert tower["category"] == "Gaming"


@pytest.mark.asyncio
async def test_list_towers_filter_status(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /api/v1/towers/?status=Paused returns only Paused towers."""
    db_session.add(_make_tower(_HASH_A, status=TowerStatus.ACTIVE))
    db_session.add(_make_tower(_HASH_B, status=TowerStatus.PAUSED))
    await db_session.commit()

    response = await api_client.get("/api/v1/towers/", params={"status": "Paused"})

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["towers"][0]["status"] == "Paused"
    assert data["towers"][0]["bundle_hash"] == _HASH_B


@pytest.mark.asyncio
async def test_list_towers_filter_invalid_category(api_client: httpx.AsyncClient) -> None:
    """GET /api/v1/towers/?category=Invalid returns 422 validation error."""
    response = await api_client.get("/api/v1/towers/", params={"category": "Invalid"})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_towers_filter_invalid_status(api_client: httpx.AsyncClient) -> None:
    """GET /api/v1/towers/?status=Unknown returns 422 validation error."""
    response = await api_client.get("/api/v1/towers/", params={"status": "Unknown"})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/towers/{bundle_hash}/  — detail endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_tower_found(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /api/v1/towers/{hash}/ returns full detail for an existing tower."""
    tower = _make_tower(_HASH_A, category=TowerCategory.BUSINESS, total_price=899.50, ml_id="ML-99")
    db_session.add(tower)
    await db_session.commit()
    await db_session.refresh(tower)

    response = await api_client.get(f"/api/v1/towers/{_HASH_A}/")

    assert response.status_code == 200
    data = response.json()
    assert data["bundle_hash"] == _HASH_A
    assert data["category"] == "Business"
    assert data["status"] == "Active"
    assert data["ml_id"] == "ML-99"
    assert data["total_price"] == 899.50
    assert data["component_skus"] == {"cpu": "CPU-SKU-001", "ram": "RAM-SKU-002"}
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_get_tower_not_found(api_client: httpx.AsyncClient) -> None:
    """GET /api/v1/towers/{hash}/ returns 404 for a non-existent bundle hash."""
    response = await api_client.get(f"/api/v1/towers/{'z' * 64}/")

    assert response.status_code == 404
    assert response.json()["detail"] is not None


@pytest.mark.asyncio
async def test_get_tower_ml_id_none(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /api/v1/towers/{hash}/ returns null ml_id when field is unset."""
    tower = _make_tower(_HASH_A, ml_id=None)
    db_session.add(tower)
    await db_session.commit()

    response = await api_client.get(f"/api/v1/towers/{_HASH_A}/")

    assert response.status_code == 200
    assert response.json()["ml_id"] is None
