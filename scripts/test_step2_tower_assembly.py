#!/usr/bin/env python3
"""Step 2 — Tower Assembly (Inventory Architect).

For each requested tier (Home, Business, Gaming):
  1. Loads inventory from Step 1 output (or fetches fresh from API).
  2. Selects components using tier strategy (cheapest / balanced / premium).
  3. Validates compatibility via ``CompatibilityEngine``.
  4. Checks uniqueness via ``UniquenessEngine``.
  5. Persists tower builds to the ``published_towers`` table.

Visible output:
  - Per-tier component table (role → SKU, name, price).
  - Compatibility validation result.
  - Bundle hash and total price.

Usage:
    uv run python scripts/test_step2_tower_assembly.py
    uv run python scripts/test_step2_tower_assembly.py --tiers Home Gaming
    uv run python scripts/test_step2_tower_assembly.py --fresh
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure the project root is on sys.path so ``orchestrator`` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from _test_utils import (
    build_base_parser,
    load_step_output,
    print_error,
    print_header,
    print_info,
    print_key_value,
    print_step_summary,
    print_subheader,
    print_success,
    print_table,
    save_step_output,
)


async def _fetch_fresh_inventory() -> dict[str, object]:
    """Fetch inventory directly from the API (bypass Step 1 output).

    Returns:
        Inventory data dict with ``inventory`` and ``specs_cache`` keys.
    """
    from orchestrator.core.config import get_settings
    from orchestrator.schemas.product import ComponentCategory
    from orchestrator.services.aiecommerce import AIEcommerceClient

    settings = get_settings()
    client = AIEcommerceClient(settings)

    categories = [
        ComponentCategory.CPU,
        ComponentCategory.MOTHERBOARD,
        ComponentCategory.RAM,
        ComponentCategory.GPU,
        ComponentCategory.SSD,
        ComponentCategory.PSU,
        ComponentCategory.CASE,
        ComponentCategory.FAN,
    ]

    inventory: dict[str, list[dict[str, object]]] = {}
    specs_cache: dict[str, dict[str, object]] = {}

    for cat in categories:
        response = await client.list_products(category=cat, active_only=True, has_stock=True)
        inventory[cat.value] = [item.model_dump() for item in response.results]
        for item in response.results:
            if str(item.id) not in specs_cache:
                detail = await client.get_product_detail(item.id)
                specs_cache[str(item.id)] = detail.model_dump()

    return {"inventory": inventory, "specs_cache": specs_cache}


async def main() -> None:
    """Run tower assembly for each requested tier."""
    parser = build_base_parser("Step 2 — Tower Assembly (Inventory Architect)")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Fetch inventory fresh from API instead of using Step 1 output.",
    )
    args = parser.parse_args()

    print_header("Step 2 — Tower Assembly (Inventory Architect)")

    # Load or fetch inventory
    if args.fresh:
        print_info("Fetching fresh inventory from API...")
        data = await _fetch_fresh_inventory()
    else:
        print_info("Loading inventory from Step 1 output...")
        data = load_step_output("step1_inventory.json")

    raw_inventory = data["inventory"]
    raw_specs = data.get("specs_cache", {})
    assert isinstance(raw_inventory, dict)
    assert isinstance(raw_specs, dict)

    # Reconstruct Pydantic models from raw data
    from orchestrator.schemas.product import (
        ComponentSelection,
        ProductDetail,
        ProductListItem,
        TowerBuild,
    )

    inventory_by_category: dict[str, list[ProductListItem]] = {}
    for cat_val, items_raw in raw_inventory.items():
        inventory_by_category[cat_val] = [
            ProductListItem.model_validate(item) for item in items_raw
        ]

    specs_cache: dict[int, ProductDetail] = {}
    for pid_str, spec_raw in raw_specs.items():
        specs_cache[int(pid_str)] = ProductDetail.model_validate(spec_raw)

    # Show inventory summary
    print_subheader("Available Inventory")
    inv_rows: list[list[str]] = []
    for cat_val, items in inventory_by_category.items():
        if items:
            prices = [i.price for i in items]
            inv_rows.append(
                [
                    cat_val.upper(),
                    str(len(items)),
                    f"${min(prices):.2f}",
                    f"${max(prices):.2f}",
                ]
            )
        else:
            inv_rows.append([cat_val.upper(), "0", "-", "-"])
    print_table(["Category", "Count", "Min Price", "Max Price"], inv_rows)

    # Fetch full specs for all products if not already loaded
    if not specs_cache:
        print_info("Specs cache is empty — fetching details from API...")
        from orchestrator.core.config import get_settings
        from orchestrator.services.aiecommerce import AIEcommerceClient

        settings = get_settings()
        client = AIEcommerceClient(settings)
        for items in inventory_by_category.values():
            for item in items:
                if item.id not in specs_cache:
                    detail = await client.get_product_detail(item.id)
                    specs_cache[item.id] = detail

    # Import assembly services
    from orchestrator.core.database import async_session_factory, create_tables
    from orchestrator.services.compatibility import CompatibilityEngine
    from orchestrator.services.component_audit_repository import ComponentAuditRepository
    from orchestrator.services.tower_repository import TowerRepository
    from orchestrator.services.uniqueness import UniquenessEngine

    # Ensure tables exist
    await create_tables()

    compat_engine = CompatibilityEngine()
    completed_builds: list[dict[str, object]] = []
    error_count = 0

    async with async_session_factory() as session:
        tower_repo = TowerRepository(session)
        audit_repo = ComponentAuditRepository(session)
        uniqueness_engine = UniquenessEngine(tower_repo)

        # Upsert audit records
        for items in inventory_by_category.values():
            for item in items:
                await audit_repo.upsert(item.sku, item.category.value, item.total_available_stock)

        for tier in args.tiers:
            print_subheader(f"Tier: {tier}")

            try:
                # Import the private selection helper
                from orchestrator.graph.nodes.inventory_architect import (
                    _build_alternatives,
                    _build_component_skus,
                    _collect_skus,
                    _select_components_for_tier,
                )

                # Select components
                build: TowerBuild = await _select_components_for_tier(
                    tier, inventory_by_category, specs_cache, audit_repo
                )
                print_success(f"Component selection complete for {tier}")

                # Show component table
                components: list[list[str]] = []
                for role in ["cpu", "motherboard", "ram", "ssd", "psu", "case", "gpu"]:
                    comp: ComponentSelection | None = getattr(build, role, None)
                    if comp is not None:
                        components.append(
                            [
                                role.upper(),
                                comp.sku,
                                comp.normalized_name[:35],
                                f"${comp.price:.2f}",
                            ]
                        )
                for i, fan in enumerate(build.fans):
                    components.append(
                        [
                            f"FAN #{i + 1}",
                            fan.sku,
                            fan.normalized_name[:35],
                            f"${fan.price:.2f}",
                        ]
                    )
                print_table(["Role", "SKU", "Name", "Price"], components)

                # Validate compatibility
                compat_errors = compat_engine.validate_build(build)
                if compat_errors:
                    for err in compat_errors:
                        print_error(f"Compatibility: {err}")
                    error_count += 1
                    continue
                print_success("Compatibility validation passed")

                # Check uniqueness
                alternatives = _build_alternatives(inventory_by_category, specs_cache, build)
                build = await uniqueness_engine.ensure_unique(build, alternatives)
                print_success(f"Uniqueness check passed — hash: {build.bundle_hash[:16]}...")

                # Persist tower
                from orchestrator.models.tower import (
                    PublishedTower,
                    TowerCategory,
                    TowerStatus,
                )

                tower = PublishedTower(
                    bundle_hash=build.bundle_hash,
                    category=TowerCategory(tier),
                    status=TowerStatus.ACTIVE,
                    component_skus=_build_component_skus(build),
                    total_price=build.total_price,
                )
                await tower_repo.create(tower)
                await audit_repo.record_bundle_usage(_collect_skus(build))

                print_success("Tower persisted to database")

                # Summary for this tier
                print_key_value("Bundle Hash", build.bundle_hash)
                print_key_value("Total Price", f"${build.total_price:.2f}")
                print_key_value("Components", len(components))

                completed_builds.append(build.model_dump())

            except Exception as exc:
                print_error(f"Tier '{tier}' failed: {exc}")
                error_count += 1

        await session.commit()

    # Save output for next step
    print_subheader("Saving Output")
    save_step_output(
        "step2_towers.json",
        {
            "completed_builds": completed_builds,
            "tiers_processed": args.tiers,
        },
    )

    print_step_summary("Step 2 — Tower Assembly", len(completed_builds), error_count)


if __name__ == "__main__":
    asyncio.run(main())
