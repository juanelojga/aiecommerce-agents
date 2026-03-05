"""Tests for ComponentAuditRepository."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.models.component_audit import ComponentAudit
from orchestrator.services.component_audit_repository import ComponentAuditRepository


@pytest.fixture
async def repo(db_session: AsyncSession) -> ComponentAuditRepository:
    """Return a ComponentAuditRepository wired to the test DB session."""
    return ComponentAuditRepository(db_session)


@pytest.mark.asyncio
async def test_upsert_creates_new(repo: ComponentAuditRepository, db_session: AsyncSession) -> None:
    """Upsert inserts a new record when the SKU does not yet exist."""
    audit = await repo.upsert(sku="AMD-RYZEN-5600X", category="CPU", stock_level=10)

    assert audit.sku == "AMD-RYZEN-5600X"
    assert audit.category == "CPU"
    assert audit.stock_level == 10
    assert audit.bundle_count == 0
    assert audit.last_bundled_date is None

    # Verify it was persisted.
    fetched = await db_session.get(ComponentAudit, "AMD-RYZEN-5600X")
    assert fetched is not None
    assert fetched.stock_level == 10


@pytest.mark.asyncio
async def test_upsert_updates_existing(
    repo: ComponentAuditRepository, db_session: AsyncSession
) -> None:
    """Upsert updates category and stock_level for an already-existing SKU."""
    await repo.upsert(sku="AMD-RYZEN-5600X", category="CPU", stock_level=5)

    updated = await repo.upsert(sku="AMD-RYZEN-5600X", category="CPU", stock_level=20)

    assert updated.sku == "AMD-RYZEN-5600X"
    assert updated.stock_level == 20
    # bundle_count must not be reset by upsert.
    assert updated.bundle_count == 0


@pytest.mark.asyncio
async def test_upsert_updates_category(repo: ComponentAuditRepository) -> None:
    """Upsert updates the category when the SKU already exists."""
    await repo.upsert(sku="SOME-SKU", category="OldCategory", stock_level=1)
    updated = await repo.upsert(sku="SOME-SKU", category="NewCategory", stock_level=1)

    assert updated.category == "NewCategory"


@pytest.mark.asyncio
async def test_get_by_sku_returns_record(repo: ComponentAuditRepository) -> None:
    """get_by_sku returns the correct record after it has been upserted."""
    await repo.upsert(sku="NVIDIA-RTX3080", category="GPU", stock_level=3)

    result = await repo.get_by_sku("NVIDIA-RTX3080")

    assert result is not None
    assert result.sku == "NVIDIA-RTX3080"
    assert result.category == "GPU"


@pytest.mark.asyncio
async def test_get_by_sku_returns_none_for_missing(repo: ComponentAuditRepository) -> None:
    """get_by_sku returns None when the SKU has no audit record."""
    result = await repo.get_by_sku("NONEXISTENT-SKU")

    assert result is None


@pytest.mark.asyncio
async def test_record_bundle_usage(
    repo: ComponentAuditRepository, db_session: AsyncSession
) -> None:
    """record_bundle_usage increments bundle_count and sets last_bundled_date."""
    await repo.upsert(sku="AMD-RYZEN-5600X", category="CPU", stock_level=10)
    await repo.upsert(sku="NVIDIA-RTX3080", category="GPU", stock_level=5)

    before = datetime.now(UTC)
    await repo.record_bundle_usage(["AMD-RYZEN-5600X", "NVIDIA-RTX3080"])
    after = datetime.now(UTC)

    cpu = await db_session.get(ComponentAudit, "AMD-RYZEN-5600X")
    gpu = await db_session.get(ComponentAudit, "NVIDIA-RTX3080")

    assert cpu is not None
    assert cpu.bundle_count == 1
    assert cpu.last_bundled_date is not None
    # Timestamps may lose tz info in SQLite; compare naive datetimes.
    cpu_ts = cpu.last_bundled_date.replace(tzinfo=None)
    assert before.replace(tzinfo=None) <= cpu_ts <= after.replace(tzinfo=None)

    assert gpu is not None
    assert gpu.bundle_count == 1


@pytest.mark.asyncio
async def test_record_bundle_usage_increments_multiple_times(
    repo: ComponentAuditRepository, db_session: AsyncSession
) -> None:
    """Calling record_bundle_usage twice increments bundle_count to 2."""
    await repo.upsert(sku="AMD-RYZEN-5600X", category="CPU", stock_level=10)

    await repo.record_bundle_usage(["AMD-RYZEN-5600X"])
    await repo.record_bundle_usage(["AMD-RYZEN-5600X"])

    cpu = await db_session.get(ComponentAudit, "AMD-RYZEN-5600X")
    assert cpu is not None
    assert cpu.bundle_count == 2


@pytest.mark.asyncio
async def test_record_bundle_usage_skips_unknown_skus(
    repo: ComponentAuditRepository,
) -> None:
    """record_bundle_usage silently ignores SKUs without an audit record."""
    # Should not raise even though the SKU does not exist.
    await repo.record_bundle_usage(["UNKNOWN-SKU"])


@pytest.mark.asyncio
async def test_get_least_recently_bundled(repo: ComponentAuditRepository) -> None:
    """get_least_recently_bundled returns components ordered oldest-first."""
    await repo.upsert(sku="CPU-A", category="CPU", stock_level=1)
    await repo.upsert(sku="CPU-B", category="CPU", stock_level=1)
    await repo.upsert(sku="CPU-C", category="CPU", stock_level=1)

    # Give each component a distinct last_bundled_date.
    old_date = datetime(2024, 1, 1, tzinfo=UTC)
    mid_date = datetime(2024, 6, 1, tzinfo=UTC)
    new_date = datetime(2025, 1, 1, tzinfo=UTC)

    cpu_a = await repo.get_by_sku("CPU-A")
    cpu_b = await repo.get_by_sku("CPU-B")
    cpu_c = await repo.get_by_sku("CPU-C")
    assert cpu_a is not None
    assert cpu_b is not None
    assert cpu_c is not None

    cpu_a.last_bundled_date = new_date
    cpu_b.last_bundled_date = old_date
    cpu_c.last_bundled_date = mid_date
    await repo._session.flush()

    results = await repo.get_least_recently_bundled("CPU", limit=3)

    assert [r.sku for r in results] == ["CPU-B", "CPU-C", "CPU-A"]


@pytest.mark.asyncio
async def test_get_least_recently_bundled_null_dates_first(
    repo: ComponentAuditRepository,
) -> None:
    """Components never bundled (null last_bundled_date) appear before dated ones."""
    await repo.upsert(sku="GPU-A", category="GPU", stock_level=1)
    await repo.upsert(sku="GPU-B", category="GPU", stock_level=1)

    # Give GPU-B a bundled date; GPU-A stays null.
    gpu_b = await repo.get_by_sku("GPU-B")
    assert gpu_b is not None
    gpu_b.last_bundled_date = datetime(2024, 6, 1, tzinfo=UTC)
    await repo._session.flush()

    results = await repo.get_least_recently_bundled("GPU", limit=10)

    skus = [r.sku for r in results]
    assert skus.index("GPU-A") < skus.index("GPU-B")


@pytest.mark.asyncio
async def test_get_least_recently_bundled_limit(repo: ComponentAuditRepository) -> None:
    """get_least_recently_bundled respects the limit parameter."""
    for i in range(5):
        await repo.upsert(sku=f"CPU-{i}", category="CPU", stock_level=1)

    results = await repo.get_least_recently_bundled("CPU", limit=3)

    assert len(results) == 3


@pytest.mark.asyncio
async def test_get_least_recently_bundled_filters_by_category(
    repo: ComponentAuditRepository,
) -> None:
    """get_least_recently_bundled only returns records matching the category."""
    await repo.upsert(sku="CPU-X", category="CPU", stock_level=1)
    await repo.upsert(sku="GPU-X", category="GPU", stock_level=1)

    results = await repo.get_least_recently_bundled("CPU", limit=10)

    assert all(r.category == "CPU" for r in results)
    assert len(results) == 1
