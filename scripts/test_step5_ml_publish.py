#!/usr/bin/env python3
"""Step 5 — MercadoLibre Publishing (Channel Manager).

For each completed build with bundles and creative assets:
  1. Calculates final price via ``PricingCalculator``.
  2. Generates listing title and description via ``ListingContentGenerator``.
  3. Uploads media to MercadoLibre (images + video).
  4. Creates the ML listing via ``MercadoLibreClient``.
  5. Stores ML ID in ``published_towers`` and ``published_bundles``.

Supports ``--dry-run`` to compute pricing and listing content without calling ML API.

Visible output:
  - Per-build pricing breakdown (component cost, margin, fees, final price).
  - Generated listing title and description preview.
  - ML listing ID and permalink (when not in dry-run).

Usage:
    uv run python scripts/test_step5_ml_publish.py --dry-run
    uv run python scripts/test_step5_ml_publish.py
    uv run python scripts/test_step5_ml_publish.py --tiers Home
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
    print_warning,
    save_step_output,
)


def _find_matching_bundle(
    build: dict[str, object],
    bundles: list[dict[str, object]],
) -> dict[str, object] | None:
    """Find the bundle matching a build by tower_hash.

    Args:
        build: Serialised TowerBuild dict.
        bundles: List of serialised BundleBuild dicts.

    Returns:
        Matching bundle dict or None.
    """
    tower_hash = str(build.get("bundle_hash", ""))
    if not tower_hash:
        return None
    for bundle in bundles:
        if str(bundle.get("tower_hash", "")) == tower_hash:
            return bundle
    return None


def _collect_build_assets(
    tower_hash: str,
    assets: list[dict[str, object]],
) -> tuple[list[str], str | None]:
    """Collect image and video URLs for a build from the assets list.

    Args:
        tower_hash: SHA-256 hash identifying the tower build.
        assets: List of serialised creative asset dicts.

    Returns:
        Tuple of (image_urls, video_url).
    """
    image_urls: list[str] = []
    video_url: str | None = None

    for asset in assets:
        media_type = str(asset.get("media_type", ""))
        url = str(asset.get("url", ""))
        if not url:
            continue
        if media_type == "image":
            image_urls.append(url)
        elif media_type == "video" and video_url is None:
            video_url = url

    return image_urls, video_url


async def main() -> None:
    """Run MercadoLibre publishing for each completed build."""
    parser = build_base_parser("Step 5 — MercadoLibre Publishing (Channel Manager)")
    args = parser.parse_args()

    print_header("Step 5 — MercadoLibre Publishing (Channel Manager)")

    # Load all prior data
    print_info("Loading data from Step 4 output...")
    asset_data = load_step_output("step4_assets.json")
    completed_builds: list[dict[str, object]] = asset_data.get("completed_builds", [])
    completed_bundles: list[dict[str, object]] = asset_data.get("completed_bundles", [])
    completed_assets: list[dict[str, object]] = asset_data.get("completed_assets", [])

    if not completed_builds:
        print_error("No completed builds found in Step 4 output.")
        sys.exit(1)

    # Filter to requested tiers
    builds_to_process = [b for b in completed_builds if str(b.get("tier", "")) in args.tiers]
    print_success(
        f"Loaded {len(builds_to_process)} build(s), "
        f"{len(completed_bundles)} bundle(s), "
        f"{len(completed_assets)} asset(s)"
    )

    if args.dry_run:
        print_warning("DRY RUN — pricing & content will be computed but ML API will NOT be called")

    from orchestrator.core.config import get_settings
    from orchestrator.services.listing_content import ListingContentGenerator
    from orchestrator.services.pricing import PricingCalculator

    settings = get_settings()
    pricing = PricingCalculator(
        assembly_margin_percent=settings.ASSEMBLY_MARGIN_PERCENT,
        ml_fee_percent=settings.ML_FEE_PERCENT,
    )
    content_generator = ListingContentGenerator()
    published_listings: list[dict[str, object]] = []
    error_count = 0

    for build in builds_to_process:
        tier = str(build.get("tier", ""))
        tower_hash = str(build.get("bundle_hash", ""))
        matching_bundle = _find_matching_bundle(build, completed_bundles)

        print_subheader(f"Tier: {tier} (Tower: {tower_hash[:16]}...)")

        # Pricing
        if matching_bundle:
            final_price = pricing.calculate_bundle_price(build, matching_bundle)
        else:
            final_price = pricing.calculate_tower_price(build)

        tower_total = float(build.get("total_price", 0))  # type: ignore[arg-type]
        peripheral_total = (
            float(matching_bundle.get("total_peripheral_price", 0))  # type: ignore[arg-type]
            if matching_bundle
            else 0.0
        )
        component_cost = tower_total + peripheral_total

        print_key_value("Component Cost", f"${component_cost:.2f}")
        print_key_value("Assembly Margin", f"{settings.ASSEMBLY_MARGIN_PERCENT}%")
        print_key_value("ML Fee", f"{settings.ML_FEE_PERCENT}%")
        print_key_value("Final Price", f"${final_price:.2f}")

        # Listing content
        title = content_generator.generate_title(build, matching_bundle)
        description = content_generator.generate_description(build, matching_bundle)

        print_subheader("Listing Content")
        print_key_value("Title", title)
        print_key_value("Title Length", f"{len(title)} chars (max 60)")
        print_info(f"Description preview:\n{description[:300]}...")

        # Asset summary
        image_urls, video_url = _collect_build_assets(tower_hash, completed_assets)
        print_subheader("Media Assets")
        print_key_value("Images", f"{len(image_urls)} images")
        print_key_value("Video", video_url[:60] + "..." if video_url else "None")

        if args.dry_run:
            print_success("DRY RUN — Skipping ML API calls")
            published_listings.append(
                {
                    "ml_id": f"dry-run-{tower_hash[:8]}",
                    "tier": tier,
                    "title": title,
                    "price": final_price,
                    "status": "dry_run",
                    "permalink": "https://placeholder.test/listing",
                    "tower_hash": tower_hash,
                }
            )
            continue

        # Real ML API calls
        from orchestrator.core.database import async_session_factory, create_tables
        from orchestrator.schemas.mercadolibre import MLListingRequest, MLPicture
        from orchestrator.services.bundle_repository import BundleRepository
        from orchestrator.services.mercadolibre import MercadoLibreClient
        from orchestrator.services.tower_repository import TowerRepository

        await create_tables()
        ml_client = MercadoLibreClient(settings)

        # Upload images
        ml_pictures: list[MLPicture] = []
        for img_url in image_urls:
            try:
                ml_img_id = await ml_client.upload_image(img_url)
                ml_pictures.append(MLPicture(source=ml_img_id))
                print_success(f"Image uploaded: {ml_img_id}")
            except Exception as exc:
                print_error(f"Image upload failed: {exc}")
                error_count += 1

        # Upload video
        video_id: str | None = None
        if video_url:
            try:
                video_id = await ml_client.upload_video(video_url)
                print_success(f"Video uploaded: {video_id}")
            except Exception as exc:
                print_error(f"Video upload failed: {exc}")
                error_count += 1

        # Create listing
        ml_category_id = "MLA1649"
        listing_request = MLListingRequest(
            title=title,
            category_id=ml_category_id,
            price=final_price,
            description=description,
            pictures=ml_pictures,
            video_id=video_id,
        )

        try:
            ml_response = await ml_client.create_listing(listing_request)
            print_success(f"Listing created: {ml_response.id}")
            print_key_value("ML ID", ml_response.id)
            print_key_value("Status", ml_response.status)
            print_key_value("Permalink", ml_response.permalink)

            # Store ML ID in database
            async with async_session_factory() as session:
                tower_repo = TowerRepository(session)
                bundle_repo = BundleRepository(session)
                await tower_repo.update_ml_id(tower_hash, ml_response.id)
                if matching_bundle:
                    bundle_id = str(matching_bundle.get("bundle_id", ""))
                    if bundle_id:
                        await bundle_repo.update_ml_id(bundle_id, ml_response.id)
                await session.commit()
                print_success("ML ID stored in database")

            published_listings.append(
                {
                    "ml_id": ml_response.id,
                    "tier": tier,
                    "title": ml_response.title,
                    "price": ml_response.price,
                    "status": ml_response.status,
                    "permalink": ml_response.permalink,
                    "tower_hash": tower_hash,
                }
            )

        except Exception as exc:
            print_error(f"Listing creation failed: {exc}")
            error_count += 1

    # Save output
    print_subheader("Saving Output")
    save_step_output(
        "step5_listings.json",
        {
            "published_listings": published_listings,
        },
    )

    print_step_summary("Step 5 — ML Publishing", len(published_listings), error_count)


if __name__ == "__main__":
    asyncio.run(main())
