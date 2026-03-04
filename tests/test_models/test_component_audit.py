"""Tests for the ComponentAudit ORM model."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.models.component_audit import ComponentAudit


@pytest.mark.asyncio
async def test_component_audit_create(db_session: AsyncSession) -> None:
    """ComponentAudit can be persisted and read back with correct values."""
    audit = ComponentAudit(
        sku="AMD-RYZEN-5600X",
        category="CPU",
    )
    db_session.add(audit)
    await db_session.commit()
    await db_session.refresh(audit)

    fetched = await db_session.get(ComponentAudit, "AMD-RYZEN-5600X")
    assert fetched is not None
    assert fetched.sku == "AMD-RYZEN-5600X"
    assert fetched.category == "CPU"


@pytest.mark.asyncio
async def test_component_audit_bundle_count_default(db_session: AsyncSession) -> None:
    """Default bundle_count is 0 when not explicitly provided."""
    audit = ComponentAudit(
        sku="NVIDIA-RTX3080",
        category="GPU",
    )
    db_session.add(audit)
    await db_session.commit()
    await db_session.refresh(audit)

    assert audit.bundle_count == 0


@pytest.mark.asyncio
async def test_component_audit_stock_level_default(db_session: AsyncSession) -> None:
    """Default stock_level is 0 when not explicitly provided."""
    audit = ComponentAudit(
        sku="SAMSUNG-980-PRO",
        category="Storage",
    )
    db_session.add(audit)
    await db_session.commit()
    await db_session.refresh(audit)

    assert audit.stock_level == 0


@pytest.mark.asyncio
async def test_component_audit_last_bundled_date_nullable(db_session: AsyncSession) -> None:
    """last_bundled_date is nullable and defaults to None."""
    audit = ComponentAudit(
        sku="CORSAIR-RM850X",
        category="PSU",
    )
    db_session.add(audit)
    await db_session.commit()
    await db_session.refresh(audit)

    assert audit.last_bundled_date is None


@pytest.mark.asyncio
async def test_component_audit_update_fields(db_session: AsyncSession) -> None:
    """bundle_count and last_bundled_date can be updated after creation."""
    audit = ComponentAudit(
        sku="LG-27GP850-B",
        category="Monitor",
    )
    db_session.add(audit)
    await db_session.commit()

    now = datetime(2025, 6, 1, tzinfo=UTC)
    audit.bundle_count = 5
    audit.last_bundled_date = now
    await db_session.commit()
    await db_session.refresh(audit)

    assert audit.bundle_count == 5
    # SQLite strips timezone info on retrieval; compare naive UTC datetime.
    assert audit.last_bundled_date is not None
    assert audit.last_bundled_date.replace(tzinfo=None) == now.replace(tzinfo=None)
