"""Repository for async CRUD operations on PublishedTower records."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.models.tower import PublishedTower, TowerCategory, TowerStatus

logger = logging.getLogger(__name__)


class TowerRepository:
    """Data-access layer for the ``published_towers`` table.

    All methods use the provided async SQLAlchemy session, which must be
    managed (committed / rolled back / closed) by the caller.

    Args:
        session: An open :class:`~sqlalchemy.ext.asyncio.AsyncSession` bound
            to the target database.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialise the repository with an async database session.

        Args:
            session: Active async SQLAlchemy session.
        """
        self._session = session

    async def get_by_hash(self, bundle_hash: str) -> PublishedTower | None:
        """Return the tower matching the given hash, or ``None`` if absent.

        Args:
            bundle_hash: SHA-256 hash that serves as the primary key.

        Returns:
            The matching :class:`~orchestrator.models.tower.PublishedTower`
            instance, or ``None`` if no record exists for *bundle_hash*.
        """
        return await self._session.get(PublishedTower, bundle_hash)

    async def list_all(
        self,
        *,
        category: TowerCategory | None = None,
        status: TowerStatus | None = None,
    ) -> list[PublishedTower]:
        """Return all towers, optionally filtered by category and/or status.

        Args:
            category: When provided, only towers of this category are returned.
            status: When provided, only towers with this status are returned.

        Returns:
            A list of :class:`~orchestrator.models.tower.PublishedTower`
            instances matching the supplied filters (may be empty).
        """
        stmt = select(PublishedTower)
        if category is not None:
            stmt = stmt.where(PublishedTower.category == category)
        if status is not None:
            stmt = stmt.where(PublishedTower.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, tower: PublishedTower) -> PublishedTower:
        """Persist a new tower record and return it after flushing.

        The session is flushed (but **not** committed) so the ORM can
        populate server-side defaults (e.g., ``created_at``).  The caller
        is responsible for committing the transaction.

        Args:
            tower: A transient :class:`~orchestrator.models.tower.PublishedTower`
                instance to be inserted.

        Returns:
            The same instance after being added to the session and flushed.
        """
        self._session.add(tower)
        await self._session.flush()
        await self._session.refresh(tower)
        logger.debug("Created tower with hash=%s", tower.bundle_hash)
        return tower

    async def update_status(self, bundle_hash: str, status: TowerStatus) -> PublishedTower | None:
        """Update the status of an existing tower.

        Args:
            bundle_hash: Primary key of the tower to update.
            status: The new :class:`~orchestrator.models.tower.TowerStatus`
                value to apply.

        Returns:
            The updated :class:`~orchestrator.models.tower.PublishedTower`
            instance, or ``None`` if no record matches *bundle_hash*.
        """
        tower = await self.get_by_hash(bundle_hash)
        if tower is None:
            return None
        tower.status = status
        await self._session.flush()
        await self._session.refresh(tower)
        logger.debug("Updated tower hash=%s status=%s", bundle_hash, status)
        return tower

    async def hash_exists(self, bundle_hash: str) -> bool:
        """Return ``True`` if a tower with the given hash already exists.

        Useful for uniqueness checks before inserting a new record.

        Args:
            bundle_hash: SHA-256 hash to check.

        Returns:
            ``True`` when a matching record is found, ``False`` otherwise.
        """
        tower = await self.get_by_hash(bundle_hash)
        return tower is not None
