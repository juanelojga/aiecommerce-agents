"""Tests for CreativeAssetRepository CRUD operations."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.services.creative_asset_repository import CreativeAssetRepository
from tests.factories import make_creative_asset

# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_asset(db_session: AsyncSession) -> None:
    """Single asset is persisted and receives an auto-incremented ID."""
    repo = CreativeAssetRepository(db_session)
    asset = make_creative_asset(tower_hash="a" * 64)

    created = await repo.create(asset)
    await db_session.commit()

    assert created.id is not None
    assert created.tower_hash == "a" * 64


# ---------------------------------------------------------------------------
# create_many
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_many_assets(db_session: AsyncSession) -> None:
    """Batch creation persists all assets and assigns IDs to each."""
    repo = CreativeAssetRepository(db_session)
    assets = [
        make_creative_asset(tower_hash="b" * 64, url="https://example.com/1.png"),
        make_creative_asset(tower_hash="b" * 64, url="https://example.com/2.png"),
        make_creative_asset(tower_hash="b" * 64, url="https://example.com/3.png"),
    ]

    created = await repo.create_many(assets)
    await db_session.commit()

    assert len(created) == 3
    assert all(a.id is not None for a in created)


# ---------------------------------------------------------------------------
# get_by_tower_hash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_tower_hash(db_session: AsyncSession) -> None:
    """Returns all assets linked to a given tower hash."""
    repo = CreativeAssetRepository(db_session)
    db_session.add(make_creative_asset(tower_hash="c" * 64, url="https://example.com/c1.png"))
    db_session.add(make_creative_asset(tower_hash="c" * 64, url="https://example.com/c2.png"))
    db_session.add(make_creative_asset(tower_hash="d" * 64, url="https://example.com/d1.png"))
    await db_session.commit()

    result = await repo.get_by_tower_hash("c" * 64)

    assert len(result) == 2
    assert all(a.tower_hash == "c" * 64 for a in result)


@pytest.mark.asyncio
async def test_get_by_tower_hash_empty(db_session: AsyncSession) -> None:
    """Returns an empty list when no assets match the given tower hash."""
    repo = CreativeAssetRepository(db_session)

    result = await repo.get_by_tower_hash("z" * 64)

    assert result == []


# ---------------------------------------------------------------------------
# get_by_bundle_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_bundle_id(db_session: AsyncSession) -> None:
    """Returns all assets linked to a given bundle ID."""
    repo = CreativeAssetRepository(db_session)
    db_session.add(make_creative_asset(bundle_id="e" * 64, url="https://example.com/e1.png"))
    db_session.add(make_creative_asset(bundle_id="e" * 64, url="https://example.com/e2.png"))
    db_session.add(make_creative_asset(bundle_id="f" * 64, url="https://example.com/f1.png"))
    await db_session.commit()

    result = await repo.get_by_bundle_id("e" * 64)

    assert len(result) == 2
    assert all(a.bundle_id == "e" * 64 for a in result)
