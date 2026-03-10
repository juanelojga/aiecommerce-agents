#!/usr/bin/env python3
"""Step 1 — Product API Communication.

Fetches inventory from the AIEcommerce API for all 8 core component
categories, retrieves detailed specs for a sample product per category,
and saves the full inventory + specs to ``scripts/output/step1_inventory.json``.

Visible output:
  - Per-category product count table.
  - Sample product details (SKU, name, price, stock, spec keys).
  - Total product count across all categories.

Usage:
    uv run python scripts/test_step1_product_api.py
    uv run python scripts/test_step1_product_api.py --include-peripherals
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure the project root is on sys.path so ``orchestrator`` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from _test_utils import (
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

# Core component categories (tower assembly).
_CORE_CATEGORIES = ["cpu", "motherboard", "ram", "gpu", "ssd", "psu", "case", "fan"]

# Peripheral categories (bundle creation).
_PERIPHERAL_CATEGORIES = ["keyboard", "mouse", "monitor", "speakers"]


async def main() -> None:
    """Fetch inventory from the AIEcommerce API and display results."""
    parser = argparse.ArgumentParser(
        description="Step 1 — Fetch inventory from the AIEcommerce product API."
    )
    parser.add_argument(
        "--include-peripherals",
        action="store_true",
        help="Also fetch peripheral categories (keyboard, mouse, monitor, speakers).",
    )
    args = parser.parse_args()

    print_header("Step 1 — Product API Communication")

    from orchestrator.core.config import get_settings
    from orchestrator.schemas.product import ComponentCategory
    from orchestrator.services.aiecommerce import AIEcommerceClient

    settings = get_settings()
    client = AIEcommerceClient(settings)

    categories = list(_CORE_CATEGORIES)
    if args.include_peripherals:
        categories.extend(_PERIPHERAL_CATEGORIES)

    print_info(f"API URL: {settings.AIECOMMERCE_API_URL}")
    print_info(f"Categories to fetch: {', '.join(categories)}\n")

    # ------------------------------------------------------------------
    # Fetch inventory per category
    # ------------------------------------------------------------------
    inventory: dict[str, list[dict[str, object]]] = {}
    specs_cache: dict[int, dict[str, object]] = {}
    summary_rows: list[list[str]] = []
    total_products = 0
    error_count = 0

    for cat_value in categories:
        cat = ComponentCategory(cat_value)
        try:
            response = await client.list_products(category=cat, active_only=True, has_stock=True)
            items = response.results
            inventory[cat_value] = [item.model_dump() for item in items]
            total_products += len(items)
            summary_rows.append(
                [
                    cat_value.upper(),
                    str(len(items)),
                    str(response.count),
                    "OK" if items else "EMPTY",
                ]
            )
            print_success(f"{cat_value.upper()}: {len(items)} products fetched")
        except Exception as exc:
            summary_rows.append([cat_value.upper(), "0", "?", f"ERROR: {exc}"])
            print_error(f"{cat_value.upper()}: {exc}")
            inventory[cat_value] = []
            error_count += 1

    # ------------------------------------------------------------------
    # Display inventory summary table
    # ------------------------------------------------------------------
    print_subheader("Inventory Summary")
    print_table(
        ["Category", "In Page", "Total", "Status"],
        summary_rows,
    )
    print_key_value("\nTotal products fetched", total_products)

    # ------------------------------------------------------------------
    # Fetch detailed specs for one sample product per category
    # ------------------------------------------------------------------
    print_subheader("Sample Product Details (1 per category)")

    sample_details: list[list[str]] = []
    for cat_value in categories:
        items_raw = inventory.get(cat_value, [])
        if not items_raw:
            continue

        sample = items_raw[0]
        assert isinstance(sample, dict)
        product_id = int(str(sample["id"]))
        try:
            detail = await client.get_product_detail(product_id)
            specs_cache[product_id] = detail.model_dump()
            spec_keys = list(detail.specs.keys())[:5]
            spec_preview = ", ".join(spec_keys) if spec_keys else "(no specs)"
            sample_details.append(
                [
                    cat_value.upper(),
                    str(detail.sku),
                    detail.normalized_name[:40],
                    f"${detail.price:.2f}",
                    str(detail.total_available_stock),
                    spec_preview,
                ]
            )
        except Exception as exc:
            sample_details.append(
                [
                    cat_value.upper(),
                    str(sample.get("sku", "?")),
                    str(sample.get("normalized_name", "?"))[:40],
                    str(sample.get("price", "?")),
                    "?",
                    f"ERROR: {exc}",
                ]
            )
            error_count += 1

    print_table(
        ["Category", "SKU", "Name", "Price", "Stock", "Spec Keys"],
        sample_details,
    )

    # ------------------------------------------------------------------
    # Show expanded specs for the first product
    # ------------------------------------------------------------------
    if specs_cache:
        first_id = next(iter(specs_cache))
        detail_data = specs_cache[first_id]
        print_subheader(f"Full Specs Preview — Product #{first_id}")
        specs = detail_data.get("specs", {})
        if isinstance(specs, dict):
            for key, value in list(specs.items())[:10]:
                print_key_value(str(key), str(value))
            remaining = len(specs) - 10
            if remaining > 0:
                print_info(f"... and {remaining} more spec fields")
        else:
            print_info("Specs not available as dict")

    # ------------------------------------------------------------------
    # Save output for next step
    # ------------------------------------------------------------------
    print_subheader("Saving Output")
    output_data = {
        "inventory": inventory,
        "specs_cache": {str(k): v for k, v in specs_cache.items()},
        "categories_fetched": categories,
        "total_products": total_products,
    }
    save_step_output("step1_inventory.json", output_data)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print_step_summary("Step 1 — Product API", total_products, error_count)


if __name__ == "__main__":
    asyncio.run(main())
