"""Repository for ComponentAudit CRUD operations."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.models.component_audit import ComponentAudit


class ComponentAuditRepository:
    """Repository for ComponentAudit CRUD operations.

    Handles create, update, and query operations on the ``component_audit``
    table to support catalogue rotation (FR-1.7) and uniqueness retry (FR-6.2).

    Args:
        session: Async SQLAlchemy session used for all database interactions.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with an async database session.

        Args:
            session: The async SQLAlchemy session to use for queries.
        """
        self._session = session

    async def get_by_sku(self, sku: str) -> ComponentAudit | None:
        """Retrieve the audit record for a component SKU.

        Args:
            sku: Unique stock-keeping unit identifier to look up.

        Returns:
            The matching :class:`ComponentAudit` record, or ``None`` if not found.
        """
        return await self._session.get(ComponentAudit, sku)

    async def upsert(self, sku: str, category: str, stock_level: int) -> ComponentAudit:
        """Create or update a component audit entry.

        If a record for *sku* already exists, its ``category`` and
        ``stock_level`` are updated in place.  Otherwise a new record is
        inserted with default ``bundle_count`` of 0.

        Args:
            sku: Unique stock-keeping unit identifier.
            category: Component category (e.g. ``"CPU"``).
            stock_level: Current stock quantity from the catalogue service.

        Returns:
            The created or updated :class:`ComponentAudit` instance.
        """
        audit = await self._session.get(ComponentAudit, sku)
        if audit is None:
            audit = ComponentAudit(sku=sku, category=category, stock_level=stock_level)
            self._session.add(audit)
        else:
            audit.category = category
            audit.stock_level = stock_level
        await self._session.flush()
        await self._session.refresh(audit)
        return audit

    async def record_bundle_usage(self, skus: list[str]) -> None:
        """Update last_bundled_date and increment bundle_count for each SKU.

        Only SKUs that already have an audit record are updated; unknown SKUs
        are silently skipped.

        Args:
            skus: List of stock-keeping unit identifiers included in the bundle.
        """
        now = datetime.now(UTC)
        for sku in skus:
            audit = await self._session.get(ComponentAudit, sku)
            if audit is not None:
                audit.last_bundled_date = now
                audit.bundle_count += 1
        await self._session.flush()

    async def get_least_recently_bundled(
        self,
        category: str,
        limit: int = 10,
    ) -> list[ComponentAudit]:
        """Return components ordered by oldest last_bundled_date for rotation.

        Components that have never been bundled (``last_bundled_date IS NULL``)
        are returned first, followed by those with the oldest dates.

        Args:
            category: Component category to filter by.
            limit: Maximum number of records to return (default ``10``).

        Returns:
            List of :class:`ComponentAudit` records ordered null-first then
            ascending by ``last_bundled_date``.
        """
        stmt = (
            select(ComponentAudit)
            .where(ComponentAudit.category == category)
            .order_by(
                ComponentAudit.last_bundled_date.is_(None).desc(),
                ComponentAudit.last_bundled_date.asc(),
            )
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
