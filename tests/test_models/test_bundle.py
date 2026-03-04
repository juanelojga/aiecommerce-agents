"""Tests for the PublishedBundle ORM model."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.models.bundle import PublishedBundle
from orchestrator.models.tower import PublishedTower, TowerCategory


@pytest.fixture
async def persisted_tower(db_session: AsyncSession) -> PublishedTower:
    """Insert a minimal PublishedTower and return it for FK tests."""
    tower = PublishedTower(
        bundle_hash="t" * 64,
        category=TowerCategory.GAMING,
        component_skus={"cpu": "AMD-RYZEN-5600X"},
    )
    db_session.add(tower)
    await db_session.commit()
    await db_session.refresh(tower)
    return tower


@pytest.mark.asyncio
async def test_published_bundle_create(
    db_session: AsyncSession, persisted_tower: PublishedTower
) -> None:
    """Bundle can be persisted with a valid FK reference to a tower."""
    bundle = PublishedBundle(
        bundle_id="b" * 64,
        tower_hash=persisted_tower.bundle_hash,
        peripheral_skus={"monitor": "LG-27GP850-B", "keyboard": "MX-KEYS"},
    )
    db_session.add(bundle)
    await db_session.commit()
    await db_session.refresh(bundle)

    fetched = await db_session.get(PublishedBundle, "b" * 64)
    assert fetched is not None
    assert fetched.bundle_id == "b" * 64
    assert fetched.tower_hash == persisted_tower.bundle_hash


@pytest.mark.asyncio
async def test_published_bundle_peripheral_skus_json(
    db_session: AsyncSession, persisted_tower: PublishedTower
) -> None:
    """JSON peripheral_skus field stores and retrieves the mapping correctly."""
    skus = {"monitor": "DELL-U2722D", "mouse": "MX-MASTER3", "headset": "HD-560S"}
    bundle = PublishedBundle(
        bundle_id="c" * 64,
        tower_hash=persisted_tower.bundle_hash,
        peripheral_skus=skus,
    )
    db_session.add(bundle)
    await db_session.commit()
    await db_session.refresh(bundle)

    fetched = await db_session.get(PublishedBundle, "c" * 64)
    assert fetched is not None
    assert fetched.peripheral_skus == skus


@pytest.mark.asyncio
async def test_published_bundle_optional_ml_id(
    db_session: AsyncSession, persisted_tower: PublishedTower
) -> None:
    """ml_id is nullable and defaults to None when not provided."""
    bundle = PublishedBundle(
        bundle_id="d" * 64,
        tower_hash=persisted_tower.bundle_hash,
        peripheral_skus={"monitor": "MONITOR-SKU"},
    )
    db_session.add(bundle)
    await db_session.commit()
    await db_session.refresh(bundle)

    assert bundle.ml_id is None
