"""LangGraph node: Channel Manager (Agent 4).

Implements FR-4.1 through FR-4.4:

- FR-4.1: Calculate final listing price via ``PricingCalculator``.
- FR-4.3: Create ML listing with title, description, price, images, video.
- FR-4.4: Store ``mercadolibre_id`` in the Local Registry.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from orchestrator.core.config import get_settings
from orchestrator.core.database import async_session_factory
from orchestrator.core.exceptions import MercadoLibreError
from orchestrator.schemas.mercadolibre import MLListingRequest, MLPicture
from orchestrator.services.bundle_repository import BundleRepository
from orchestrator.services.listing_content import ListingContentGenerator
from orchestrator.services.mercadolibre import MercadoLibreClient
from orchestrator.services.pricing import PricingCalculator
from orchestrator.services.tower_repository import TowerRepository

if TYPE_CHECKING:
    from orchestrator.graph.state import GraphState

logger = logging.getLogger(__name__)

# MercadoLibre category for assembled PCs.
_ML_CATEGORY_ID = "MLA1649"


# ---------------------------------------------------------------------------
# Public node function
# ---------------------------------------------------------------------------


async def channel_manager_node(state: GraphState) -> dict[str, object]:
    """LangGraph node: Channel Manager (Agent 4). FR-4.1-FR-4.4.

    For each completed build with creative assets, calculates final
    listing price, generates listing content, uploads media to ML,
    creates the listing, and stores the ML ID in the Local Registry.

    Args:
        state: Current graph state with completed_builds, completed_bundles,
            and completed_assets from previous agents.

    Returns:
        State update dict with published_listings, errors, and run_status.
    """
    if not state.completed_builds:
        logger.info("No completed_builds in state; returning empty listings.")
        return {
            "published_listings": [],
            "errors": [],
            "run_status": "completed",
        }

    settings = get_settings()
    pricing = PricingCalculator(
        assembly_margin_percent=settings.ASSEMBLY_MARGIN_PERCENT,
        ml_fee_percent=settings.ML_FEE_PERCENT,
    )
    content_generator = ListingContentGenerator()
    ml_client = MercadoLibreClient(settings)

    errors: list[str] = []
    published_listings: list[dict[str, object]] = []

    async with async_session_factory() as session:
        tower_repo = TowerRepository(session)
        bundle_repo = BundleRepository(session)

        for build in state.completed_builds:
            tier = str(build.get("tier", ""))
            tower_hash = str(build.get("bundle_hash", ""))

            # Find matching bundle for this build.
            matching_bundle = _find_matching_bundle(build, state.completed_bundles)

            # FR-4.1: Calculate final listing price.
            if matching_bundle:
                price = pricing.calculate_bundle_price(build, matching_bundle)
            else:
                price = pricing.calculate_tower_price(build)

            # Generate listing content (title and description).
            title = content_generator.generate_title(build, matching_bundle)
            description = content_generator.generate_description(build, matching_bundle)

            # Collect creative assets for this build.
            image_urls, video_url = _collect_build_assets(tower_hash, state.completed_assets)

            # Upload media to MercadoLibre.
            ml_pictures: list[MLPicture] = []
            for img_url in image_urls:
                try:
                    ml_img_id = await ml_client.upload_image(img_url)
                    ml_pictures.append(MLPicture(source=ml_img_id))
                except MercadoLibreError as exc:
                    _append_build_error(errors, tier, f"Image upload failed: {exc.message}")

            video_id: str | None = None
            if video_url:
                try:
                    video_id = await ml_client.upload_video(video_url)
                except MercadoLibreError as exc:
                    _append_build_error(errors, tier, f"Video upload failed: {exc.message}")

            # FR-4.3: Create ML listing.
            listing_request = MLListingRequest(
                title=title,
                category_id=_ML_CATEGORY_ID,
                price=price,
                description=description,
                pictures=ml_pictures,
                video_id=video_id,
            )

            try:
                ml_response = await ml_client.create_listing(listing_request)
            except MercadoLibreError as exc:
                _append_build_error(errors, tier, f"Listing creation failed: {exc.message}")
                continue

            # FR-4.4: Store ML ID in Local Registry.
            await tower_repo.update_ml_id(tower_hash, ml_response.id)

            if matching_bundle:
                bundle_id = str(matching_bundle.get("bundle_id", ""))
                if bundle_id:
                    await bundle_repo.update_ml_id(bundle_id, ml_response.id)

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

            logger.info(
                "Tier '%s': Published listing %s (price=%.2f).",
                tier,
                ml_response.id,
                ml_response.price,
            )

        await session.commit()

    run_status: Literal["pending", "running", "completed", "failed"] = (
        "completed" if published_listings else "failed"
    )
    return {
        "published_listings": published_listings,
        "errors": errors,
        "run_status": run_status,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _collect_build_assets(
    tower_hash: str,
    assets: list[dict[str, object]],
) -> tuple[list[str], str | None]:
    """Collect image URLs and video URL for a specific build.

    Iterates through creative assets produced by the Creative Director
    node and filters for assets belonging to the given ``tower_hash``.

    Args:
        tower_hash: SHA-256 hash identifying the tower build.
        assets: List of serialised creative asset dicts from the graph state.

    Returns:
        A tuple of (image_urls, video_url).  ``video_url`` is ``None`` when
        no video asset is found.
    """
    image_urls: list[str] = []
    video_url: str | None = None

    for asset in assets:
        if str(asset.get("tower_hash", "")) != tower_hash:
            continue
        media_type = str(asset.get("media_type", ""))
        url = str(asset.get("url", ""))
        if not url:
            continue
        if media_type == "image":
            image_urls.append(url)
        elif media_type == "video" and video_url is None:
            video_url = url

    return image_urls, video_url


def _find_matching_bundle(
    build: dict[str, object],
    bundles: list[dict[str, object]],
) -> dict[str, object] | None:
    """Find the bundle matching a build by tower_hash.

    Args:
        build: Serialised ``TowerBuild`` dict from the Inventory Architect.
        bundles: List of serialised ``BundleBuild`` dicts from the graph state.

    Returns:
        The matching bundle dict, or ``None`` if no match is found.
    """
    tower_hash = str(build.get("bundle_hash", ""))
    if not tower_hash:
        return None
    for bundle in bundles:
        if str(bundle.get("tower_hash", "")) == tower_hash:
            return bundle
    return None


def _append_build_error(errors: list[str], tier: str, detail: str) -> None:
    """Append a formatted error message for a specific tier.

    Args:
        errors: Mutable list of accumulated error strings.
        tier: The tier name that encountered the error.
        detail: The error detail message.
    """
    msg = f"Tier '{tier}': {detail}"
    errors.append(msg)
    logger.warning(msg)
