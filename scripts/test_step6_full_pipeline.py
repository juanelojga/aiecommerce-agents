#!/usr/bin/env python3
"""Step 6 — Full Pipeline (End-to-End).

Runs the complete LangGraph workflow exactly as the trigger endpoint does:
  1. Inventory Architect → Tower Assembly.
  2. Bundle Creator → Peripheral Bundling.
  3. Creative Director → Image/Video Generation.
  4. Channel Manager → MercadoLibre Publishing.

Displays a summary of each stage's output from the final ``GraphState``.

Usage:
    uv run python scripts/test_step6_full_pipeline.py
    uv run python scripts/test_step6_full_pipeline.py --tiers Home Business
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure the project root is on sys.path so ``orchestrator`` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from _test_utils import (
    build_base_parser,
    print_error,
    print_header,
    print_info,
    print_key_value,
    print_step_summary,
    print_subheader,
    print_success,
    print_table,
    print_warning,
    save_step_output,
)


async def main() -> None:
    """Run the full LangGraph assembly pipeline end-to-end."""
    parser = build_base_parser("Step 6 — Full Pipeline (End-to-End)")
    args = parser.parse_args()

    print_header("Step 6 — Full Pipeline (End-to-End)")
    print_info(f"Tiers: {', '.join(args.tiers)}")

    # Ensure database tables exist
    from orchestrator.core.database import create_tables

    await create_tables()
    print_success("Database tables verified")

    # Build and invoke the full graph
    from orchestrator.graph.workflow import build_assembly_graph

    print_subheader("Invoking LangGraph Workflow")
    print_info("This will run all 4 agents in sequence:")
    print_info("  1. Inventory Architect → Tower Assembly")
    print_info("  2. Bundle Creator → Peripheral Bundling")
    print_info("  3. Creative Director → Image/Video Generation")
    print_info("  4. Channel Manager → MercadoLibre Publishing")
    print_info("")

    graph = build_assembly_graph()
    result = await graph.ainvoke({"requested_tiers": args.tiers})

    # Extract results from graph state
    completed_builds: list[dict[str, object]] = result.get("completed_builds", [])
    completed_bundles: list[dict[str, object]] = result.get("completed_bundles", [])
    completed_assets: list[dict[str, object]] = result.get("completed_assets", [])
    published_listings: list[dict[str, object]] = result.get("published_listings", [])
    errors: list[str] = result.get("errors", [])
    run_status: str = str(result.get("run_status", "unknown"))

    # Stage 1: Tower Assembly results
    print_subheader("Stage 1 — Tower Assembly Results")
    if completed_builds:
        tower_rows: list[list[str]] = []
        for build in completed_builds:
            tier = str(build.get("tier", ""))
            bundle_hash = str(build.get("bundle_hash", ""))
            total_price = float(build.get("total_price", 0))  # type: ignore[arg-type]
            cpu_name = ""
            cpu = build.get("cpu")
            if isinstance(cpu, dict):
                cpu_name = str(cpu.get("normalized_name", ""))[:30]
            tower_rows.append(
                [
                    tier,
                    bundle_hash[:16] + "...",
                    cpu_name,
                    f"${total_price:.2f}",
                ]
            )
        print_table(["Tier", "Hash", "CPU", "Total Price"], tower_rows)
        print_success(f"{len(completed_builds)} tower(s) assembled")
    else:
        print_warning("No towers assembled")

    # Stage 2: Bundle Creation results
    print_subheader("Stage 2 — Bundle Creation Results")
    if completed_bundles:
        bundle_rows: list[list[str]] = []
        for bundle in completed_bundles:
            tier = str(bundle.get("tier", ""))
            bundle_id = str(bundle.get("bundle_id", ""))
            periph_count = len(bundle.get("peripherals", []))  # type: ignore[arg-type]
            total_periph = float(bundle.get("total_peripheral_price", 0))  # type: ignore[arg-type]
            bundle_rows.append(
                [
                    tier,
                    bundle_id[:16] + "...",
                    str(periph_count),
                    f"${total_periph:.2f}",
                ]
            )
        print_table(["Tier", "Bundle ID", "Peripherals", "Periph. Price"], bundle_rows)
        print_success(f"{len(completed_bundles)} bundle(s) created")
    else:
        print_warning("No bundles created")

    # Stage 3: Creative Asset results
    print_subheader("Stage 3 — Creative Asset Results")
    if completed_assets:
        image_count = sum(1 for a in completed_assets if str(a.get("media_type", "")) == "image")
        video_count = sum(1 for a in completed_assets if str(a.get("media_type", "")) == "video")
        print_key_value("Images Generated", image_count)
        print_key_value("Videos Generated", video_count)
        print_key_value("Total Assets", len(completed_assets))
        print_success(f"{len(completed_assets)} asset(s) generated")
    else:
        print_warning("No creative assets generated")

    # Stage 4: ML Publishing results
    print_subheader("Stage 4 — MercadoLibre Publishing Results")
    if published_listings:
        listing_rows: list[list[str]] = []
        for listing in published_listings:
            tier = str(listing.get("tier", ""))
            ml_id = str(listing.get("ml_id", ""))
            title = str(listing.get("title", ""))[:40]
            price = float(listing.get("price", 0))  # type: ignore[arg-type]
            status = str(listing.get("status", ""))
            listing_rows.append([tier, ml_id, title, f"${price:.2f}", status])
        print_table(["Tier", "ML ID", "Title", "Price", "Status"], listing_rows)
        print_success(f"{len(published_listings)} listing(s) published")
    else:
        print_warning("No listings published")

    # Errors
    if errors:
        print_subheader("Errors Encountered")
        for err in errors:
            print_error(err)

    # Overall status
    print_subheader("Pipeline Status")
    print_key_value("Run Status", run_status)
    print_key_value("Towers", len(completed_builds))
    print_key_value("Bundles", len(completed_bundles))
    print_key_value("Assets", len(completed_assets))
    print_key_value("Listings", len(published_listings))
    print_key_value("Errors", len(errors))

    # Save output
    save_step_output(
        "step6_full_pipeline.json",
        {
            "run_status": run_status,
            "completed_builds": completed_builds,
            "completed_bundles": completed_bundles,
            "completed_assets": completed_assets,
            "published_listings": published_listings,
            "errors": errors,
        },
    )

    total_success = (
        len(completed_builds)
        + len(completed_bundles)
        + len(completed_assets)
        + len(published_listings)
    )
    print_step_summary("Step 6 — Full Pipeline", total_success, len(errors))


if __name__ == "__main__":
    asyncio.run(main())
