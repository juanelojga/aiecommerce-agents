"""Tests for TowerRepository CRUD operations."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.models.tower import PublishedTower, TowerCategory, TowerStatus
from orchestrator.services.tower_repository import TowerRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tower(bundle_hash: str, category: TowerCategory = TowerCategory.GAMING) -> PublishedTower:
    """Return a transient PublishedTower with sensible defaults."""
    return PublishedTower(
        bundle_hash=bundle_hash,
        category=category,
        component_skus={"cpu": "AMD-RYZEN-5600X", "gpu": "NVIDIA-RTX3080"},
    )


# ---------------------------------------------------------------------------
# get_by_hash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_hash_returns_tower(db_session: AsyncSession) -> None:
    """get_by_hash returns the tower when the hash exists."""
    repo = TowerRepository(db_session)
    tower = _make_tower("a" * 64)
    db_session.add(tower)
    await db_session.commit()

    result = await repo.get_by_hash("a" * 64)

    assert result is not None
    assert result.bundle_hash == "a" * 64


@pytest.mark.asyncio
async def test_get_by_hash_returns_none_when_missing(db_session: AsyncSession) -> None:
    """get_by_hash returns None when no tower matches the hash."""
    repo = TowerRepository(db_session)

    result = await repo.get_by_hash("z" * 64)

    assert result is None


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_all_returns_all_towers(db_session: AsyncSession) -> None:
    """list_all with no filters returns every persisted tower."""
    repo = TowerRepository(db_session)
    towers = [
        _make_tower("b" * 64, TowerCategory.GAMING),
        _make_tower("c" * 64, TowerCategory.HOME),
        _make_tower("d" * 64, TowerCategory.BUSINESS),
    ]
    for t in towers:
        db_session.add(t)
    await db_session.commit()

    result = await repo.list_all()

    assert len(result) == 3


@pytest.mark.asyncio
async def test_list_all_filters_by_category(db_session: AsyncSession) -> None:
    """list_all with category filter returns only matching towers."""
    repo = TowerRepository(db_session)
    db_session.add(_make_tower("e" * 64, TowerCategory.GAMING))
    db_session.add(_make_tower("f" * 64, TowerCategory.HOME))
    await db_session.commit()

    result = await repo.list_all(category=TowerCategory.GAMING)

    assert len(result) == 1
    assert result[0].category == TowerCategory.GAMING


@pytest.mark.asyncio
async def test_list_all_filters_by_status(db_session: AsyncSession) -> None:
    """list_all with status filter returns only matching towers."""
    repo = TowerRepository(db_session)
    active = _make_tower("g" * 64)
    paused = _make_tower("h" * 64)
    db_session.add(active)
    db_session.add(paused)
    await db_session.commit()

    # Pause one tower directly
    paused.status = TowerStatus.PAUSED
    await db_session.commit()

    active_result = await repo.list_all(status=TowerStatus.ACTIVE)
    paused_result = await repo.list_all(status=TowerStatus.PAUSED)

    assert len(active_result) == 1
    assert active_result[0].bundle_hash == "g" * 64
    assert len(paused_result) == 1
    assert paused_result[0].bundle_hash == "h" * 64


@pytest.mark.asyncio
async def test_list_all_filters_by_category_and_status(db_session: AsyncSession) -> None:
    """list_all with both filters applied returns only exact matches."""
    repo = TowerRepository(db_session)
    gaming_active = _make_tower("i" * 64, TowerCategory.GAMING)
    gaming_paused = _make_tower("j" * 64, TowerCategory.GAMING)
    home_active = _make_tower("k" * 64, TowerCategory.HOME)
    db_session.add(gaming_active)
    db_session.add(gaming_paused)
    db_session.add(home_active)
    await db_session.commit()

    gaming_paused.status = TowerStatus.PAUSED
    await db_session.commit()

    result = await repo.list_all(category=TowerCategory.GAMING, status=TowerStatus.ACTIVE)

    assert len(result) == 1
    assert result[0].bundle_hash == "i" * 64


@pytest.mark.asyncio
async def test_list_all_returns_empty_list_when_no_towers(db_session: AsyncSession) -> None:
    """list_all returns an empty list when the table is empty."""
    repo = TowerRepository(db_session)

    result = await repo.list_all()

    assert result == []


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_persists_tower(db_session: AsyncSession) -> None:
    """create adds the tower to the database and returns it."""
    repo = TowerRepository(db_session)
    tower = _make_tower("l" * 64)

    created = await repo.create(tower)
    await db_session.commit()

    assert created.bundle_hash == "l" * 64
    fetched = await db_session.get(PublishedTower, "l" * 64)
    assert fetched is not None
    assert fetched.category == TowerCategory.GAMING


@pytest.mark.asyncio
async def test_create_sets_default_status(db_session: AsyncSession) -> None:
    """Newly created tower defaults to ACTIVE status."""
    repo = TowerRepository(db_session)
    tower = _make_tower("m" * 64)

    created = await repo.create(tower)
    await db_session.commit()

    assert created.status == TowerStatus.ACTIVE


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_status_changes_status(db_session: AsyncSession) -> None:
    """update_status persists the new status and returns the tower."""
    repo = TowerRepository(db_session)
    tower = _make_tower("n" * 64)
    db_session.add(tower)
    await db_session.commit()

    updated = await repo.update_status("n" * 64, TowerStatus.PAUSED)
    await db_session.commit()

    assert updated is not None
    assert updated.status == TowerStatus.PAUSED


@pytest.mark.asyncio
async def test_update_status_returns_none_for_missing_hash(db_session: AsyncSession) -> None:
    """update_status returns None when the hash does not exist."""
    repo = TowerRepository(db_session)

    result = await repo.update_status("z" * 64, TowerStatus.PAUSED)

    assert result is None


# ---------------------------------------------------------------------------
# hash_exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hash_exists_returns_true_when_present(db_session: AsyncSession) -> None:
    """hash_exists returns True when a matching tower exists."""
    repo = TowerRepository(db_session)
    db_session.add(_make_tower("o" * 64))
    await db_session.commit()

    assert await repo.hash_exists("o" * 64) is True


@pytest.mark.asyncio
async def test_hash_exists_returns_false_when_absent(db_session: AsyncSession) -> None:
    """hash_exists returns False when no tower matches the hash."""
    repo = TowerRepository(db_session)

    assert await repo.hash_exists("z" * 64) is False


# ---------------------------------------------------------------------------
# update_ml_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_tower_ml_id_success(db_session: AsyncSession) -> None:
    """update_ml_id sets ml_id on an existing tower and returns it."""
    repo = TowerRepository(db_session)
    tower = _make_tower("p" * 64)
    db_session.add(tower)
    await db_session.commit()

    updated = await repo.update_ml_id("p" * 64, "ML-123456789")
    await db_session.commit()

    assert updated is not None
    assert updated.ml_id == "ML-123456789"


@pytest.mark.asyncio
async def test_update_tower_ml_id_not_found(db_session: AsyncSession) -> None:
    """update_ml_id returns None when no tower matches the hash."""
    repo = TowerRepository(db_session)

    result = await repo.update_ml_id("z" * 64, "ML-999")

    assert result is None
