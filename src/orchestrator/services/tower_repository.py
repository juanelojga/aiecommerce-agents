"""Tower repository for CRUD operations on the published_towers table.

Provides an async data-access layer for :class:`PublishedTower` records,
following the repository pattern so callers depend on an abstraction rather
than raw SQLAlchemy sessions.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.models.tower import PublishedTower, TowerCategory, TowerStatus

logger = logging.getLogger(__name__)


class TowerRepository:
    """Repository for PublishedTower CRUD operations.

    Args:
        session: Async SQLAlchemy session used for all database access.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialise with an async database session.

        Args:
            session: The SQLAlchemy async session to use for queries.
        """
        self._session = session

    async def get_by_hash(self, bundle_hash: str) -> PublishedTower | None:
        """Retrieve a tower by its bundle hash.

        Args:
            bundle_hash: The SHA-256 hex digest that identifies the tower.

        Returns:
            The matching :class:`PublishedTower`, or ``None`` if not found.
        """
        result = await self._session.execute(
            select(PublishedTower).where(PublishedTower.bundle_hash == bundle_hash)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        category: TowerCategory | None = None,
        status: TowerStatus | None = None,
    ) -> list[PublishedTower]:
        """List towers with optional category/status filters.

        Args:
            category: When provided, only towers with this category are returned.
            status: When provided, only towers with this status are returned.

        Returns:
            A list of :class:`PublishedTower` records matching the filters.
        """
        stmt = select(PublishedTower)
        if category is not None:
            stmt = stmt.where(PublishedTower.category == category)
        if status is not None:
            stmt = stmt.where(PublishedTower.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, tower: PublishedTower) -> PublishedTower:
        """Persist a new tower to the registry.

        Args:
            tower: The :class:`PublishedTower` instance to insert.

        Returns:
            The persisted tower (with any server-generated defaults populated).
        """
        self._session.add(tower)
        await self._session.flush()
        await self._session.refresh(tower)
        return tower

    async def update_status(self, bundle_hash: str, status: TowerStatus) -> PublishedTower | None:
        """Update the status of a tower (e.g. Active → Paused).

        Args:
            bundle_hash: Hash identifying the tower to update.
            status: The new status to apply.

        Returns:
            The updated :class:`PublishedTower`, or ``None`` if not found.
        """
        tower = await self.get_by_hash(bundle_hash)
        if tower is None:
            return None
        tower.status = status
        await self._session.flush()
        await self._session.refresh(tower)
        return tower

    async def hash_exists(self, bundle_hash: str) -> bool:
        """Check if a bundle hash already exists in the registry.

        Performs a lightweight existence check without loading the full model,
        enabling efficient duplicate detection.

        Args:
            bundle_hash: The SHA-256 hex digest to look up.

        Returns:
            ``True`` if a tower with this hash is stored, ``False`` otherwise.
        """
        result = await self._session.execute(
            select(PublishedTower.bundle_hash).where(PublishedTower.bundle_hash == bundle_hash)
        )
        return result.scalar_one_or_none() is not None
