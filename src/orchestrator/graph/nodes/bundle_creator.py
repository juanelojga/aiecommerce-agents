"""LangGraph node: Bundle Creator (Agent 2).

Implements FR-2.1 through FR-2.3 and FR-6.2:

- FR-2.1: Triggered after tower creation, adds peripherals per tier.
- FR-2.2: Tiered peripheral selection (Home/Business/Gaming).
- FR-2.3: Creates Complete Kit linking peripherals to parent tower.
- FR-6.2: Updates ``ComponentAudit`` for each peripheral SKU used.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from orchestrator.core.config import get_settings
from orchestrator.core.database import async_session_factory
from orchestrator.core.exceptions import APIClientError, InventoryError
from orchestrator.models.bundle import PublishedBundle
from orchestrator.schemas.bundle import BundleBuild, PeripheralSelection
from orchestrator.schemas.product import ComponentCategory, ProductDetail, ProductListItem
from orchestrator.services.aiecommerce import AIEcommerceClient
from orchestrator.services.bundle_hash import compute_bundle_hash
from orchestrator.services.bundle_repository import BundleRepository
from orchestrator.services.component_audit_repository import ComponentAuditRepository
from orchestrator.services.peripheral_selector import PeripheralSelector

if TYPE_CHECKING:
    from collections.abc import Sequence

    from orchestrator.graph.state import GraphState

logger = logging.getLogger(__name__)

# Peripheral categories fetched from the aiecommerce API.
_PERIPHERAL_CATEGORIES: tuple[ComponentCategory, ...] = (
    ComponentCategory.KEYBOARD,
    ComponentCategory.MOUSE,
    ComponentCategory.MONITOR,
    ComponentCategory.SPEAKERS,
)


# ---------------------------------------------------------------------------
# Public node function
# ---------------------------------------------------------------------------


async def bundle_creator_node(state: GraphState) -> dict[str, object]:
    """LangGraph node: Bundle Creator (Agent 2).

    For each completed tower build, selects tier-appropriate peripherals,
    creates a Complete Kit bundle, and persists it to the Local Registry.

    Implements FR-2.1 through FR-2.3:
    - FR-2.1: Triggered after tower creation, adds peripherals per tier.
    - FR-2.2: Tiered peripheral selection (Home/Business/Gaming).
    - FR-2.3: Creates Complete Kit linking peripherals to parent tower.

    Args:
        state: Current graph state with completed_builds from Agent 1.

    Returns:
        State update dict with completed_bundles, errors, and run_status.
    """
    if not state.completed_builds:
        logger.info("No completed_builds in state; returning empty bundles.")
        return {
            "completed_bundles": [],
            "errors": [],
            "run_status": "completed",
        }

    settings = get_settings()
    api_client = AIEcommerceClient(settings)
    selector = PeripheralSelector()

    errors: list[str] = []
    completed_bundles: list[dict[str, object]] = []

    # ------------------------------------------------------------------
    # Step 1: Fetch peripheral inventory and product specs.
    # ------------------------------------------------------------------
    peripheral_inventory: dict[str, list[ProductListItem]] = {}
    specs_cache: dict[int, ProductDetail] = {}

    for cat in _PERIPHERAL_CATEGORIES:
        try:
            response = await api_client.list_products(
                category=cat,
                active_only=True,
                has_stock=True,
            )
            peripheral_inventory[cat.value] = response.results
            for item in response.results:
                if item.id not in specs_cache:
                    detail = await api_client.get_product_detail(item.id)
                    specs_cache[item.id] = detail
            logger.debug(
                "Fetched %d %s peripherals from API.",
                len(response.results),
                cat.value,
            )
        except APIClientError as exc:
            msg = f"Failed to fetch {cat.value} peripheral inventory: {exc.message}"
            logger.error(msg)
            errors.append(msg)
            return {
                "completed_bundles": [],
                "errors": errors,
                "run_status": "failed",
            }

    # ------------------------------------------------------------------
    # Step 2: Open a DB session and process each build.
    # ------------------------------------------------------------------
    async with async_session_factory() as session:
        bundle_repo = BundleRepository(session)
        audit_repo = ComponentAuditRepository(session)

        for build in state.completed_builds:
            tier = str(build.get("tier", ""))
            tower_hash = str(build.get("bundle_hash", ""))

            try:
                # FR-2.2: Select tier-appropriate peripherals.
                selections = await selector.select_peripherals(
                    tier, peripheral_inventory, specs_cache
                )

                # Build peripheral_skus mapping (role → SKU).
                peripheral_skus = _build_peripheral_skus(selections)

                # Compute bundle hash from tower hash + peripheral SKUs.
                bundle_id = compute_bundle_hash(tower_hash, peripheral_skus)

                # Build the BundleBuild schema for serialisation.
                total_peripheral_price = sum(s.price for s in selections)
                bundle_build = BundleBuild(
                    tower_hash=tower_hash,
                    tier=tier,
                    peripherals=selections,
                    bundle_id=bundle_id,
                    total_peripheral_price=total_peripheral_price,
                )

                # Persist the bundle to the Local Registry.
                published_bundle = PublishedBundle(
                    bundle_id=bundle_id,
                    tower_hash=tower_hash,
                    peripheral_skus=dict(peripheral_skus),
                )
                await bundle_repo.create(published_bundle)

                # FR-6.2: Update ComponentAudit for each peripheral SKU.
                await audit_repo.record_bundle_usage(list(peripheral_skus.values()))

                completed_bundles.append(bundle_build.model_dump())
                logger.info(
                    "Successfully created %s tier bundle: %s",
                    tier,
                    bundle_id,
                )

            except InventoryError as exc:
                _append_tier_error(errors, tier, exc.message)
            except Exception as exc:
                _append_tier_error(errors, tier, str(exc))
                logger.exception("Unexpected error processing tier '%s' bundle.", tier)

        await session.commit()

    run_status: Literal["pending", "running", "completed", "failed"] = (
        "completed" if completed_bundles else "failed"
    )
    return {
        "completed_bundles": completed_bundles,
        "errors": errors,
        "run_status": run_status,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_peripheral_skus(
    selections: Sequence[PeripheralSelection],
) -> dict[str, str]:
    """Build a role → SKU mapping from peripheral selections.

    Each peripheral selection's category value is used as the role key,
    and the SKU is the corresponding value.

    Args:
        selections: Sequence of :class:`PeripheralSelection` objects.

    Returns:
        Mapping of peripheral role to SKU identifier.
    """
    skus: dict[str, str] = {}
    for sel in selections:
        skus[sel.category.value] = sel.sku
    return skus


def _append_tier_error(errors: list[str], tier: str, detail: str) -> None:
    """Append a formatted tier-scoped error message to the errors list.

    Args:
        errors: Mutable list of accumulated error strings.
        tier: The tier name that encountered the error.
        detail: The error detail message.
    """
    msg = f"Tier '{tier}': {detail}"
    errors.append(msg)
    logger.warning(msg)
