"""LangGraph node: Inventory Architect (Agent 1).

Implements FR-1.1 through FR-1.7:

- FR-1.1: Fetch inventory from the aiecommerce API, filtered by category/active/stock.
- FR-1.2: Select components for Home (cheapest), Business (balanced), Gaming (performance).
- FR-1.3: Validate technical compatibility via CompatibilityEngine.
- FR-1.4: Auto-add a standalone PSU when the selected case does not include one.
- FR-1.5: Auto-add 2-3 cooling fans for Gaming builds when the case does not include them.
- FR-1.6: Compute a SHA-256 hash and ensure uniqueness via UniquenessEngine.
- FR-1.7: Prioritise components with the oldest ``last_bundled_date`` (catalog rotation).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from orchestrator.core.config import get_settings
from orchestrator.core.database import async_session_factory
from orchestrator.core.exceptions import (
    APIClientError,
    CompatibilityError,
    InventoryError,
    UniquenessError,
)
from orchestrator.models.tower import PublishedTower, TowerCategory, TowerStatus

if TYPE_CHECKING:
    from orchestrator.graph.state import GraphState
from orchestrator.schemas.product import (
    ComponentCategory,
    ComponentSelection,
    ProductDetail,
    ProductListItem,
    TowerBuild,
)
from orchestrator.services.aiecommerce import AIEcommerceClient
from orchestrator.services.compatibility import CompatibilityEngine
from orchestrator.services.component_audit_repository import ComponentAuditRepository
from orchestrator.services.tower_repository import TowerRepository
from orchestrator.services.uniqueness import UniquenessEngine

logger = logging.getLogger(__name__)

# Categories fetched from the aiecommerce API on every run.
_INVENTORY_CATEGORIES: tuple[ComponentCategory, ...] = (
    ComponentCategory.CPU,
    ComponentCategory.MOTHERBOARD,
    ComponentCategory.RAM,
    ComponentCategory.GPU,
    ComponentCategory.SSD,
    ComponentCategory.PSU,
    ComponentCategory.CASE,
    ComponentCategory.FAN,
)

# Required categories that must have at least one component for any build to succeed.
_REQUIRED_CATEGORIES: tuple[ComponentCategory, ...] = (
    ComponentCategory.CPU,
    ComponentCategory.MOTHERBOARD,
    ComponentCategory.RAM,
    ComponentCategory.SSD,
    ComponentCategory.PSU,
    ComponentCategory.CASE,
)


# ---------------------------------------------------------------------------
# Public node function
# ---------------------------------------------------------------------------


async def inventory_architect_node(state: GraphState) -> dict[str, object]:
    """LangGraph node: Inventory Architect (Agent 1).

    Fetches inventory, selects components for each requested tier,
    validates compatibility, ensures uniqueness, and persists builds.

    Args:
        state: Current graph state with ``requested_tiers``.

    Returns:
        State update dict with ``completed_builds``, ``errors``, and ``run_status``.
    """
    if not state.requested_tiers:
        logger.info("No requested_tiers in state; returning empty result.")
        return {
            "completed_builds": [],
            "errors": [],
            "run_status": "completed",
        }

    settings = get_settings()
    api_client = AIEcommerceClient(settings)
    compat_engine = CompatibilityEngine()

    errors: list[str] = []
    completed_builds: list[dict[str, object]] = []

    # ------------------------------------------------------------------
    # Step 1: Fetch inventory and product specs for all categories.
    # ------------------------------------------------------------------
    inventory_by_category: dict[str, list[ProductListItem]] = {}
    specs_cache: dict[int, ProductDetail] = {}

    for cat in _INVENTORY_CATEGORIES:
        try:
            response = await api_client.list_products(
                category=cat,
                active_only=True,
                has_stock=True,
            )
            inventory_by_category[cat.value] = response.results
            for item in response.results:
                if item.id not in specs_cache:
                    detail = await api_client.get_product_detail(item.id)
                    specs_cache[item.id] = detail
            logger.debug(
                "Fetched %d %s components from API.",
                len(response.results),
                cat.value,
            )
        except APIClientError as exc:
            msg = f"Failed to fetch {cat.value} inventory: {exc.message}"
            logger.error(msg)
            errors.append(msg)
            return {
                "completed_builds": [],
                "errors": errors,
                "run_status": "failed",
            }

    # ------------------------------------------------------------------
    # Step 2: Open a DB session and process each tier.
    # ------------------------------------------------------------------
    async with async_session_factory() as session:
        tower_repo = TowerRepository(session)
        audit_repo = ComponentAuditRepository(session)
        uniqueness_engine = UniquenessEngine(tower_repo)

        # Upsert audit records for every fetched item so the rotation
        # mechanism has up-to-date stock levels.
        for cat_items in inventory_by_category.values():
            for item in cat_items:
                await audit_repo.upsert(
                    item.sku,
                    item.category.value,
                    item.total_available_stock,
                )

        for tier in state.requested_tiers:
            try:
                build = await _select_components_for_tier(
                    tier,
                    inventory_by_category,
                    specs_cache,
                    audit_repo,
                )

                # FR-1.3: Validate compatibility (raises CompatibilityError on failure).
                compat_engine.assert_valid(build)

                # FR-1.6: Ensure uniqueness, swapping secondary components if needed.
                alternatives = _build_alternatives(inventory_by_category, specs_cache, build)
                build = await uniqueness_engine.ensure_unique(build, alternatives)

                # Persist the validated, unique tower build to the registry.
                tower = PublishedTower(
                    bundle_hash=build.bundle_hash,
                    category=TowerCategory(tier),
                    status=TowerStatus.ACTIVE,
                    component_skus=_build_component_skus(build),
                    total_price=build.total_price,
                )
                await tower_repo.create(tower)

                # FR-6.2 / FR-1.7: Update audit usage to maintain rotation priority.
                await audit_repo.record_bundle_usage(_collect_skus(build))

                completed_builds.append(build.model_dump())
                logger.info(
                    "Successfully built %s tier tower: %s (%.2f)",
                    tier,
                    build.bundle_hash,
                    build.total_price,
                )

            except InventoryError as exc:
                _append_tier_error(errors, tier, exc.message)
            except CompatibilityError as exc:
                _append_tier_error(errors, tier, exc.message)
            except UniquenessError as exc:
                _append_tier_error(errors, tier, exc.message)
            except Exception as exc:
                _append_tier_error(errors, tier, str(exc))
                logger.exception("Unexpected error processing tier '%s'.", tier)

        await session.commit()

    run_status: Literal["pending", "running", "completed", "failed"] = (
        "completed" if completed_builds else "failed"
    )
    return {
        "completed_builds": completed_builds,
        "errors": errors,
        "run_status": run_status,
    }


# ---------------------------------------------------------------------------
# Component selection helpers
# ---------------------------------------------------------------------------


def _rotation_sort_key(item: ProductListItem) -> tuple[int, str]:
    """Return a sort key that puts never-bundled items first (FR-1.7).

    Args:
        item: The inventory item to compute the key for.

    Returns:
        A tuple ``(0, "")`` for never-bundled items (highest priority) or
        ``(1, iso_date_string)`` for previously bundled items, so that
        ISO-8601 string comparison correctly orders them oldest-first.
    """
    if item.last_bundled_date is None:
        return (0, "")
    return (1, item.last_bundled_date)


def _tier_price_key(item: ProductListItem, tier: str) -> float:
    """Return a price sort key aligned with the tier selection strategy.

    Args:
        item: The inventory item whose price to evaluate.
        tier: Target tier (``"Home"``, ``"Business"``, or ``"Gaming"``).

    Returns:
        ``item.price`` for Home (ascending = cheapest first),
        ``-item.price`` for Gaming (ascending = most-expensive first),
        or ``0.0`` for Business (price ignored; rotation order used).
    """
    if tier == "Home":
        return item.price
    if tier == "Gaming":
        return -item.price
    # Business: neutral — rotation key alone determines order
    return 0.0


def _select_item_for_tier(
    items: list[ProductListItem],
    tier: str,
) -> ProductListItem | None:
    """Apply tier selection strategy to a list of inventory items (FR-1.2, FR-1.7).

    Selection order:
    - Sort by ``(rotation_key, price_key)`` so that catalog rotation and tier
      preference are both respected.
    - **Home** — pick the first item (cheapest + oldest).
    - **Gaming** — pick the first item (most expensive + oldest).
    - **Business** — pick the middle item (balanced pricing + oldest cohort).

    Args:
        items: Available inventory items for a single component category.
        tier: Target tier name.

    Returns:
        The selected :class:`ProductListItem`, or ``None`` when *items* is empty.
    """
    if not items:
        return None

    sorted_items = sorted(
        items,
        key=lambda i: (_rotation_sort_key(i), _tier_price_key(i, tier)),
    )

    if tier == "Business":
        return sorted_items[len(sorted_items) // 2]

    # Home and Gaming both take the first item after sorting.
    return sorted_items[0]


def _make_selection(
    item: ProductListItem,
    specs_cache: dict[int, ProductDetail],
) -> ComponentSelection:
    """Create a :class:`ComponentSelection` from an inventory item.

    Args:
        item: The chosen :class:`ProductListItem`.
        specs_cache: Mapping of product ID → :class:`ProductDetail`.

    Returns:
        A :class:`ComponentSelection` with full specs populated.
    """
    return ComponentSelection(
        sku=item.sku,
        normalized_name=item.normalized_name,
        category=item.category,
        price=item.price,
        specs=specs_cache[item.id],
    )


async def _select_components_for_tier(
    tier: str,
    inventory_by_category: dict[str, list[ProductListItem]],
    specs_cache: dict[int, ProductDetail],
    audit_repo: ComponentAuditRepository,
) -> TowerBuild:
    """Select components for a specific tier using availability and priority rules.

    Applies catalog rotation (FR-1.7) and tier selection strategy (FR-1.2).
    Auto-adds PSU (FR-1.4) and Gaming fans (FR-1.5) as required.

    Args:
        tier: Target tier (``"Home"``, ``"Business"``, or ``"Gaming"``).
        inventory_by_category: Inventory items grouped by category value string.
        specs_cache: Mapping of product ID → full :class:`ProductDetail`.
        audit_repo: Component audit repository; accepted for interface consistency
            and future use (e.g. direct DB-backed rotation queries in Phase 2).

    Returns:
        A :class:`TowerBuild` with all required components selected.

    Raises:
        InventoryError: When a required component category has no available items.
    """

    # Select each required non-optional component.
    def _pick(cat: ComponentCategory) -> ComponentSelection:
        items = inventory_by_category.get(cat.value, [])
        selected = _select_item_for_tier(items, tier)
        if selected is None:
            raise InventoryError(f"No {cat.value} components available for tier '{tier}'.")
        return _make_selection(selected, specs_cache)

    cpu = _pick(ComponentCategory.CPU)
    motherboard = _pick(ComponentCategory.MOTHERBOARD)
    ram = _pick(ComponentCategory.RAM)
    ssd = _pick(ComponentCategory.SSD)
    case_sel = _pick(ComponentCategory.CASE)

    # FR-1.4: Auto-add a standalone PSU when the case does not include one.
    psu: ComponentSelection
    if _should_add_psu(case_sel.specs):
        psu = _pick(ComponentCategory.PSU)
    else:
        # Case includes an integrated PSU; still select a nominal PSU entry
        # to satisfy the TowerBuild schema.  Fall back gracefully if no PSU
        # inventory exists.
        psu_items = inventory_by_category.get(ComponentCategory.PSU.value, [])
        if psu_items:
            selected_psu = _select_item_for_tier(psu_items, tier)
            if selected_psu is None:
                raise InventoryError(
                    f"No {ComponentCategory.PSU.value} components available for tier '{tier}'."
                )
            psu = _make_selection(selected_psu, specs_cache)
        else:
            # Raise to keep builds clean; no PSU at all is a hard blocker.
            raise InventoryError(
                f"No {ComponentCategory.PSU.value} components available for tier '{tier}'."
            )

    # GPU: required only for Gaming tier.
    gpu: ComponentSelection | None = None
    if tier == "Gaming":
        gpu_items = inventory_by_category.get(ComponentCategory.GPU.value, [])
        gpu_selected = _select_item_for_tier(gpu_items, tier)
        if gpu_selected is None:
            raise InventoryError("No GPU components available for Gaming tier.")
        gpu = _make_selection(gpu_selected, specs_cache)

    # FR-1.5: Auto-add 2-3 cooling fans for Gaming when the case lacks them.
    fans: list[ComponentSelection] = []
    if _should_add_fans(tier, case_sel.specs):
        fan_items = inventory_by_category.get(ComponentCategory.FAN.value, [])
        sorted_fans = sorted(fan_items, key=_rotation_sort_key)
        for fan_item in sorted_fans[:3]:
            fans.append(_make_selection(fan_item, specs_cache))
        if not fans:
            logger.warning(
                "Gaming tier requested fan auto-add but no fans are available in inventory."
            )

    # Compute total price across all selected components.
    all_components: list[ComponentSelection] = [
        cpu,
        motherboard,
        ram,
        ssd,
        psu,
        case_sel,
        *fans,
        *([gpu] if gpu is not None else []),
    ]
    total_price = sum(c.price for c in all_components)

    return TowerBuild(
        tier=tier,
        cpu=cpu,
        motherboard=motherboard,
        ram=ram,
        gpu=gpu,
        ssd=ssd,
        psu=psu,
        case=case_sel,
        fans=fans,
        total_price=total_price,
    )


# ---------------------------------------------------------------------------
# PSU / fan auto-add helpers
# ---------------------------------------------------------------------------


def _should_add_psu(case_detail: ProductDetail) -> bool:
    """Check whether the case requires a standalone PSU (FR-1.4).

    Reads the ``includes_psu`` key from the case's spec dictionary.

    Args:
        case_detail: Full product detail of the selected case.

    Returns:
        ``True`` when the case does **not** include an integrated PSU
        (i.e., a standalone PSU must be selected from inventory).
    """
    return not bool(case_detail.specs.get("includes_psu", False))


def _should_add_fans(tier: str, case_detail: ProductDetail) -> bool:
    """Check whether extra cooling fans should be auto-added (FR-1.5).

    Fans are added only for Gaming builds when the case does not already
    include cooling fans.

    Args:
        tier: Target tier name.
        case_detail: Full product detail of the selected case.

    Returns:
        ``True`` when extra fans must be added to the build.
    """
    return tier == "Gaming" and not bool(case_detail.specs.get("includes_fans", False))


# ---------------------------------------------------------------------------
# Build persistence helpers
# ---------------------------------------------------------------------------


def _build_alternatives(
    inventory_by_category: dict[str, list[ProductListItem]],
    specs_cache: dict[int, ProductDetail],
    build: TowerBuild,
) -> dict[str, list[ComponentSelection]]:
    """Build a map of alternative components for uniqueness swap candidates.

    Only the swap categories defined by the uniqueness engine
    (SSD → RAM → PSU) are included.

    Args:
        inventory_by_category: Inventory items grouped by category value.
        specs_cache: Mapping of product ID → :class:`ProductDetail`.
        build: The current build whose primary selections are excluded.

    Returns:
        Mapping of category value string → list of alternative
        :class:`ComponentSelection` objects (excluding the already-selected SKU).
    """
    swap_categories: dict[ComponentCategory, ComponentSelection] = {
        ComponentCategory.SSD: build.ssd,
        ComponentCategory.RAM: build.ram,
        ComponentCategory.PSU: build.psu,
    }
    alternatives: dict[str, list[ComponentSelection]] = {}

    for cat, primary in swap_categories.items():
        alts = [
            _make_selection(item, specs_cache)
            for item in inventory_by_category.get(cat.value, [])
            if item.sku != primary.sku
        ]
        if alts:
            alternatives[cat.value] = alts

    return alternatives


def _build_component_skus(build: TowerBuild) -> dict[str, object]:
    """Serialise a build's component SKUs into the JSON structure for the registry.

    Args:
        build: The validated, unique :class:`TowerBuild`.

    Returns:
        A dictionary mapping component roles to their SKU values.
    """
    skus: dict[str, object] = {
        "cpu": build.cpu.sku,
        "motherboard": build.motherboard.sku,
        "ram": build.ram.sku,
        "ssd": build.ssd.sku,
        "psu": build.psu.sku,
        "case": build.case.sku,
    }
    if build.gpu is not None:
        skus["gpu"] = build.gpu.sku
    if build.fans:
        skus["fans"] = [fan.sku for fan in build.fans]
    return skus


def _collect_skus(build: TowerBuild) -> list[str]:
    """Collect all component SKUs from a build for audit recording.

    Args:
        build: The finalised tower build.

    Returns:
        A flat list of all SKU strings included in the build.
    """
    skus: list[str] = [
        build.cpu.sku,
        build.motherboard.sku,
        build.ram.sku,
        build.ssd.sku,
        build.psu.sku,
        build.case.sku,
    ]
    if build.gpu is not None:
        skus.append(build.gpu.sku)
    skus.extend(fan.sku for fan in build.fans)
    return skus


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


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
