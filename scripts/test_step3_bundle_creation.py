#!/usr/bin/env python3
"""Step 3 — Bundle Creation (Bundle Creator).

For each completed tower build from Step 2:
  1. Fetches peripheral inventory (keyboard, mouse, monitor, speakers).
  2. Selects tier-appropriate peripherals via ``PeripheralSelector``.
  3. Computes ``bundle_id`` hash.
  4. Persists bundles to the ``published_bundles`` table.

Visible output:
  - Per-tier peripheral table (role → SKU, name, price).
  - Bundle ID hash and total peripheral price.

Usage:
    uv run python scripts/test_step3_bundle_creation.py
    uv run python scripts/test_step3_bundle_creation.py --tiers Home Gaming
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


async def main() -> None:
    """Run bundle creation for each completed tower build."""
    parser = build_base_parser("Step 3 — Bundle Creation (Bundle Creator)")
    args = parser.parse_args()

    print_header("Step 3 — Bundle Creation (Bundle Creator)")

    # Load tower builds from Step 2
    print_info("Loading tower builds from Step 2 output...")
    tower_data = load_step_output("step2_towers.json")
    completed_builds: list[dict[str, object]] = tower_data["completed_builds"]

    if not completed_builds:
        print_error("No completed builds found in Step 2 output.")
        sys.exit(1)

    print_success(f"Loaded {len(completed_builds)} tower build(s)")

    # Filter to requested tiers
    builds_to_process = [b for b in completed_builds if str(b.get("tier", "")) in args.tiers]
    print_info(f"Processing {len(builds_to_process)} build(s) for tiers: {', '.join(args.tiers)}")

    # Fetch peripheral inventory
    from orchestrator.core.config import get_settings
    from orchestrator.schemas.product import ComponentCategory, ProductDetail, ProductListItem
    from orchestrator.services.aiecommerce import AIEcommerceClient

    settings = get_settings()
    client = AIEcommerceClient(settings)

    peripheral_categories = [
        ComponentCategory.KEYBOARD,
        ComponentCategory.MOUSE,
        ComponentCategory.MONITOR,
        ComponentCategory.SPEAKERS,
    ]

    print_subheader("Fetching Peripheral Inventory")

    peripheral_inventory: dict[str, list[ProductListItem]] = {}
    specs_cache: dict[int, ProductDetail] = {}

    for cat in peripheral_categories:
        try:
            response = await client.list_products(category=cat, active_only=True, has_stock=True)
            peripheral_inventory[cat.value] = response.results
            for item in response.results:
                if item.id not in specs_cache:
                    detail = await client.get_product_detail(item.id)
                    specs_cache[item.id] = detail
            print_success(f"{cat.value.upper()}: {len(response.results)} products")
        except Exception as exc:
            print_error(f"{cat.value.upper()}: {exc}")
            peripheral_inventory[cat.value] = []

    # Show peripheral inventory summary
    periph_rows: list[list[str]] = []
    for cat in peripheral_categories:
        items = peripheral_inventory.get(cat.value, [])
        if items:
            prices = [i.price for i in items]
            periph_rows.append(
                [
                    cat.value.upper(),
                    str(len(items)),
                    f"${min(prices):.2f}",
                    f"${max(prices):.2f}",
                ]
            )
        else:
            periph_rows.append([cat.value.upper(), "0", "-", "-"])
    print_table(["Category", "Count", "Min Price", "Max Price"], periph_rows)

    # Process each build
    from orchestrator.core.database import async_session_factory, create_tables
    from orchestrator.models.bundle import PublishedBundle
    from orchestrator.services.bundle_hash import compute_bundle_hash
    from orchestrator.services.bundle_repository import BundleRepository
    from orchestrator.services.component_audit_repository import ComponentAuditRepository
    from orchestrator.services.peripheral_selector import PeripheralSelector

    await create_tables()

    selector = PeripheralSelector()
    completed_bundles: list[dict[str, object]] = []
    error_count = 0

    async with async_session_factory() as session:
        bundle_repo = BundleRepository(session)
        audit_repo = ComponentAuditRepository(session)

        for build in builds_to_process:
            tier = str(build.get("tier", ""))
            tower_hash = str(build.get("bundle_hash", ""))

            print_subheader(f"Tier: {tier} (Tower: {tower_hash[:16]}...)")

            try:
                # Select peripherals
                selections = await selector.select_peripherals(
                    tier, peripheral_inventory, specs_cache
                )
                print_success(f"Selected {len(selections)} peripheral(s)")

                # Display peripheral table
                periph_detail: list[list[str]] = []
                for sel in selections:
                    periph_detail.append(
                        [
                            sel.category.value.upper(),
                            sel.sku,
                            sel.normalized_name[:35],
                            f"${sel.price:.2f}",
                        ]
                    )
                print_table(["Role", "SKU", "Name", "Price"], periph_detail)

                # Compute bundle hash
                peripheral_skus = {sel.category.value: sel.sku for sel in selections}
                bundle_id = compute_bundle_hash(tower_hash, peripheral_skus)
                print_success(f"Bundle ID: {bundle_id[:16]}...")

                # Calculate total peripheral price
                total_peripheral_price = sum(s.price for s in selections)
                print_key_value("Total Peripheral Price", f"${total_peripheral_price:.2f}")

                # Persist bundle
                published_bundle = PublishedBundle(
                    bundle_id=bundle_id,
                    tower_hash=tower_hash,
                    peripheral_skus=dict(peripheral_skus),
                )
                await bundle_repo.create(published_bundle)
                await audit_repo.record_bundle_usage(list(peripheral_skus.values()))

                print_success("Bundle persisted to database")

                # Build bundle data for output
                from orchestrator.schemas.bundle import BundleBuild

                bundle_build = BundleBuild(
                    tower_hash=tower_hash,
                    tier=tier,
                    peripherals=selections,
                    bundle_id=bundle_id,
                    total_peripheral_price=total_peripheral_price,
                )
                completed_bundles.append(bundle_build.model_dump())

            except Exception as exc:
                print_error(f"Tier '{tier}' bundle failed: {exc}")
                error_count += 1

        await session.commit()

    # Save output
    print_subheader("Saving Output")
    save_step_output(
        "step3_bundles.json",
        {
            "completed_bundles": completed_bundles,
            "completed_builds": completed_builds,
        },
    )

    print_step_summary("Step 3 — Bundle Creation", len(completed_bundles), error_count)


if __name__ == "__main__":
    asyncio.run(main())
