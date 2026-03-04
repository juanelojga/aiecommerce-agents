"""Tests for the PublishedTower ORM model."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.models.tower import PublishedTower, TowerCategory, TowerStatus


@pytest.mark.asyncio
async def test_published_tower_create(db_session: AsyncSession) -> None:
    """Tower can be persisted and read back from the database."""
    tower = PublishedTower(
        bundle_hash="a" * 64,
        category=TowerCategory.GAMING,
        component_skus={"cpu": "AMD-RYZEN-5600X", "gpu": "NVIDIA-RTX3080"},
    )
    db_session.add(tower)
    await db_session.commit()
    await db_session.refresh(tower)

    fetched = await db_session.get(PublishedTower, "a" * 64)
    assert fetched is not None
    assert fetched.bundle_hash == "a" * 64
    assert fetched.category == TowerCategory.GAMING
    assert fetched.component_skus == {"cpu": "AMD-RYZEN-5600X", "gpu": "NVIDIA-RTX3080"}


@pytest.mark.asyncio
async def test_published_tower_category_enum(db_session: AsyncSession) -> None:
    """Category field accepts only valid TowerCategory enum values."""
    for category in TowerCategory:
        tower = PublishedTower(
            bundle_hash=f"{'b' * 63}{category.value[0]}",
            category=category,
            component_skus={"cpu": "SKU-1"},
        )
        db_session.add(tower)
    await db_session.commit()

    for category in TowerCategory:
        fetched = await db_session.get(PublishedTower, f"{'b' * 63}{category.value[0]}")
        assert fetched is not None
        assert fetched.category == category


@pytest.mark.asyncio
async def test_published_tower_status_default(db_session: AsyncSession) -> None:
    """Default status is ACTIVE when not explicitly provided."""
    tower = PublishedTower(
        bundle_hash="c" * 64,
        category=TowerCategory.HOME,
        component_skus={"cpu": "INTEL-I5"},
    )
    db_session.add(tower)
    await db_session.commit()
    await db_session.refresh(tower)

    assert tower.status == TowerStatus.ACTIVE
