"""Bundle repository for CRUD operations on the published_bundles table.

Provides an async data-access layer for :class:`PublishedBundle` records,
following the repository pattern so callers depend on an abstraction rather
than raw SQLAlchemy sessions.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.models.bundle import PublishedBundle

logger = logging.getLogger(__name__)


class BundleRepository:
    """Repository for PublishedBundle CRUD operations.

    Args:
        session: Async SQLAlchemy session used for all database access.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialise with an async database session.

        Args:
            session: The SQLAlchemy async session to use for queries.
        """
        self._session = session

    async def get_by_id(self, bundle_id: str) -> PublishedBundle | None:
        """Retrieve a bundle by its bundle ID (SHA-256 hash).

        Args:
            bundle_id: The SHA-256 hex digest identifying the bundle.

        Returns:
            The matching :class:`PublishedBundle`, or ``None`` if not found.
        """
        result = await self._session.execute(
            select(PublishedBundle).where(PublishedBundle.bundle_id == bundle_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tower_hash(self, tower_hash: str) -> PublishedBundle | None:
        """Retrieve a bundle by its parent tower hash.

        Args:
            tower_hash: The tower's bundle_hash FK.

        Returns:
            The matching :class:`PublishedBundle`, or ``None`` if not found.
        """
        result = await self._session.execute(
            select(PublishedBundle).where(PublishedBundle.tower_hash == tower_hash)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[PublishedBundle]:
        """List all published bundles.

        Returns:
            A list of all :class:`PublishedBundle` records.
        """
        result = await self._session.execute(select(PublishedBundle))
        return list(result.scalars().all())

    async def create(self, bundle: PublishedBundle) -> PublishedBundle:
        """Persist a new bundle to the registry.

        Args:
            bundle: The :class:`PublishedBundle` instance to insert.

        Returns:
            The persisted bundle (with any server-generated defaults populated).
        """
        self._session.add(bundle)
        await self._session.flush()
        await self._session.refresh(bundle)
        return bundle
