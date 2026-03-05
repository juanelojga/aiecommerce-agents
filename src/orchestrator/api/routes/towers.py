"""Tower listing and detail API routes.

Exposes published towers through REST endpoints with optional filters for
category and status, and provides a detail lookup by bundle hash.
"""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.core.database import get_db_session
from orchestrator.core.exceptions import TowerNotFoundError
from orchestrator.models.tower import TowerCategory, TowerStatus
from orchestrator.schemas.tower import TowerDetail, TowerListResponse, TowerSummary
from orchestrator.services.tower_repository import TowerRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/towers", tags=["towers"])


@router.get("/", response_model=TowerListResponse)
async def list_towers(
    category: TowerCategory | None = Query(default=None, description="Filter by tower category"),
    status: TowerStatus | None = Query(default=None, description="Filter by tower status"),
    session: AsyncSession = Depends(get_db_session),
) -> TowerListResponse:
    """List all published towers with optional category and status filters.

    Args:
        category: Optional tower category to filter results (Home, Business, or Gaming).
        status: Optional tower status to filter results (Active or Paused).
        session: Injected async database session.

    Returns:
        A :class:`TowerListResponse` containing the count and list of matching towers.
    """
    repo = TowerRepository(session)
    towers = await repo.list_all(category=category, status=status)

    summaries = [
        TowerSummary(
            bundle_hash=t.bundle_hash,
            category=t.category,
            status=t.status,
            ml_id=t.ml_id,
            total_price=t.total_price,
            created_at=t.created_at,
        )
        for t in towers
    ]

    logger.debug(
        "list_towers: returned %d towers (category=%s, status=%s)",
        len(summaries),
        category,
        status,
    )
    return TowerListResponse(count=len(summaries), towers=summaries)


@router.get("/{bundle_hash}/", response_model=TowerDetail)
async def get_tower(
    bundle_hash: str,
    session: AsyncSession = Depends(get_db_session),
) -> TowerDetail:
    """Get detailed tower information by bundle hash.

    Args:
        bundle_hash: SHA-256 hex digest identifying the tower.
        session: Injected async database session.

    Returns:
        A :class:`TowerDetail` with all fields including component SKUs.

    Raises:
        TowerNotFoundError: When no tower exists for the given bundle hash (HTTP 404).
    """
    repo = TowerRepository(session)
    tower = await repo.get_by_hash(bundle_hash)

    if tower is None:
        raise TowerNotFoundError(f"Tower with hash '{bundle_hash}' not found.")

    logger.debug("get_tower: found tower %s", bundle_hash)
    return TowerDetail(
        bundle_hash=tower.bundle_hash,
        category=tower.category,
        status=tower.status,
        ml_id=tower.ml_id,
        component_skus=tower.component_skus,
        total_price=tower.total_price,
        created_at=tower.created_at,
        updated_at=tower.updated_at,
    )
