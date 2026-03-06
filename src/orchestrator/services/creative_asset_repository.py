"""Creative asset repository for CRUD operations on the creative_assets table.

Provides an async data-access layer for :class:`CreativeAsset` records,
following the repository pattern so callers depend on an abstraction rather
than raw SQLAlchemy sessions.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.models.creative_asset import CreativeAsset

logger = logging.getLogger(__name__)


class CreativeAssetRepository:
    """Repository for CreativeAsset CRUD operations.

    Args:
        session: Async SQLAlchemy session used for all database access.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialise with an async database session.

        Args:
            session: The SQLAlchemy async session to use for queries.
        """
        self._session = session

    async def create(self, asset: CreativeAsset) -> CreativeAsset:
        """Persist a new creative asset to the database.

        Args:
            asset: The :class:`CreativeAsset` instance to insert.

        Returns:
            The persisted asset (with any server-generated defaults populated).
        """
        self._session.add(asset)
        await self._session.flush()
        await self._session.refresh(asset)
        return asset

    async def create_many(self, assets: list[CreativeAsset]) -> list[CreativeAsset]:
        """Persist multiple creative assets in a single batch.

        Args:
            assets: A list of :class:`CreativeAsset` instances to insert.

        Returns:
            The persisted assets (with any server-generated defaults populated).
        """
        for asset in assets:
            self._session.add(asset)
        await self._session.flush()
        for asset in assets:
            await self._session.refresh(asset)
        return assets

    async def get_by_tower_hash(self, tower_hash: str) -> list[CreativeAsset]:
        """Retrieve all creative assets linked to a given tower hash.

        Args:
            tower_hash: The SHA-256 hash of the associated tower build.

        Returns:
            A list of :class:`CreativeAsset` records matching the tower hash.
        """
        result = await self._session.execute(
            select(CreativeAsset).where(CreativeAsset.tower_hash == tower_hash)
        )
        return list(result.scalars().all())

    async def get_by_bundle_id(self, bundle_id: str) -> list[CreativeAsset]:
        """Retrieve all creative assets linked to a given bundle ID.

        Args:
            bundle_id: The identifier of the associated bundle.

        Returns:
            A list of :class:`CreativeAsset` records matching the bundle ID.
        """
        result = await self._session.execute(
            select(CreativeAsset).where(CreativeAsset.bundle_id == bundle_id)
        )
        return list(result.scalars().all())
