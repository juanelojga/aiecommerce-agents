"""Bundle listing and detail API routes.

Exposes published bundles through REST endpoints with paginated listing
and single-bundle lookup by ID.
"""

import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.core.database import get_db_session
from orchestrator.core.exceptions import BundleNotFoundError
from orchestrator.schemas.bundle import BundleDetail, BundleListResponse, BundleSummary
from orchestrator.services.bundle_repository import BundleRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/bundles", tags=["bundles"])


async def get_bundle_repository(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[BundleRepository]:
    """Yield a :class:`BundleRepository` backed by the current DB session.

    Args:
        session: Injected async database session.

    Yields:
        A :class:`BundleRepository` instance.
    """
    yield BundleRepository(session)


@router.get("/", response_model=BundleListResponse)
async def list_bundles(
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=20, ge=1, le=100, description="Max records to return"),
    repo: BundleRepository = Depends(get_bundle_repository),
) -> BundleListResponse:
    """List all published bundles (paginated).

    Args:
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return per page.
        repo: Injected bundle repository.

    Returns:
        A :class:`BundleListResponse` with the total count and paginated bundle summaries.
    """
    all_bundles = await repo.list_all()
    page = all_bundles[skip : skip + limit]

    summaries = [
        BundleSummary(
            bundle_id=b.bundle_id,
            tower_hash=b.tower_hash,
            peripheral_skus=b.peripheral_skus,
            ml_id=b.ml_id,
            created_at=b.created_at,
        )
        for b in page
    ]

    logger.debug(
        "list_bundles: returned %d of %d bundles (skip=%d, limit=%d)",
        len(summaries),
        len(all_bundles),
        skip,
        limit,
    )
    return BundleListResponse(count=len(all_bundles), bundles=summaries)


@router.get("/{bundle_id}/", response_model=BundleDetail)
async def get_bundle(
    bundle_id: str,
    repo: BundleRepository = Depends(get_bundle_repository),
) -> BundleDetail:
    """Get a single bundle by ID.

    Args:
        bundle_id: SHA-256 hex digest identifying the bundle.
        repo: Injected bundle repository.

    Returns:
        A :class:`BundleDetail` with all fields for the matching bundle.

    Raises:
        BundleNotFoundError: When no bundle exists for the given ID (HTTP 404).
    """
    bundle = await repo.get_by_id(bundle_id)

    if bundle is None:
        raise BundleNotFoundError(f"Bundle with ID '{bundle_id}' not found.")

    logger.debug("get_bundle: found bundle %s", bundle_id)
    return BundleDetail(
        bundle_id=bundle.bundle_id,
        tower_hash=bundle.tower_hash,
        peripheral_skus=bundle.peripheral_skus,
        ml_id=bundle.ml_id,
        created_at=bundle.created_at,
        updated_at=bundle.updated_at,
    )
