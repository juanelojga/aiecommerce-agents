"""Tests for BundleRepository CRUD operations."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.services.bundle_repository import BundleRepository
from tests.factories import make_bundle, make_tower

# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_bundle(db_session: AsyncSession) -> None:
    """Bundle is persisted and retrievable after create."""
    tower = make_tower(bundle_hash="a" * 64)
    db_session.add(tower)
    await db_session.commit()

    repo = BundleRepository(db_session)
    bundle = make_bundle(bundle_id="b" * 64, tower_hash="a" * 64)

    created = await repo.create(bundle)
    await db_session.commit()

    assert created.bundle_id == "b" * 64
    fetched = await db_session.get(type(bundle), "b" * 64)
    assert fetched is not None
    assert fetched.tower_hash == "a" * 64


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_id_found(db_session: AsyncSession) -> None:
    """Returns bundle for existing ID."""
    tower = make_tower(bundle_hash="c" * 64)
    db_session.add(tower)
    bundle = make_bundle(bundle_id="d" * 64, tower_hash="c" * 64)
    db_session.add(bundle)
    await db_session.commit()

    repo = BundleRepository(db_session)
    result = await repo.get_by_id("d" * 64)

    assert result is not None
    assert result.bundle_id == "d" * 64


@pytest.mark.asyncio
async def test_get_by_id_not_found(db_session: AsyncSession) -> None:
    """Returns None for missing ID."""
    repo = BundleRepository(db_session)

    result = await repo.get_by_id("z" * 64)

    assert result is None


# ---------------------------------------------------------------------------
# get_by_tower_hash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_tower_hash_found(db_session: AsyncSession) -> None:
    """Returns bundle linked to tower."""
    tower = make_tower(bundle_hash="e" * 64)
    db_session.add(tower)
    bundle = make_bundle(bundle_id="f" * 64, tower_hash="e" * 64)
    db_session.add(bundle)
    await db_session.commit()

    repo = BundleRepository(db_session)
    result = await repo.get_by_tower_hash("e" * 64)

    assert result is not None
    assert result.tower_hash == "e" * 64


@pytest.mark.asyncio
async def test_get_by_tower_hash_not_found(db_session: AsyncSession) -> None:
    """Returns None when no bundle for tower."""
    repo = BundleRepository(db_session)

    result = await repo.get_by_tower_hash("z" * 64)

    assert result is None


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_all_empty(db_session: AsyncSession) -> None:
    """Returns empty list when no bundles."""
    repo = BundleRepository(db_session)

    result = await repo.list_all()

    assert result == []


@pytest.mark.asyncio
async def test_list_all_with_data(db_session: AsyncSession) -> None:
    """Returns all persisted bundles."""
    tower1 = make_tower(bundle_hash="g" * 64)
    tower2 = make_tower(bundle_hash="h" * 64)
    db_session.add(tower1)
    db_session.add(tower2)
    bundle1 = make_bundle(bundle_id="i" * 64, tower_hash="g" * 64)
    bundle2 = make_bundle(bundle_id="j" * 64, tower_hash="h" * 64)
    db_session.add(bundle1)
    db_session.add(bundle2)
    await db_session.commit()

    repo = BundleRepository(db_session)
    result = await repo.list_all()

    assert len(result) == 2
    ids = {b.bundle_id for b in result}
    assert ids == {"i" * 64, "j" * 64}
