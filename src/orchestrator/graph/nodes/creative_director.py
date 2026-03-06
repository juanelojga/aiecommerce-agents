"""LangGraph node: Creative Director (Agent 3).

Implements FR-3.1 through FR-3.5:

- FR-3.1: Generate 4 product images per build (one per ImageStyle).
- FR-3.2: Generate 1 product video per build.
- FR-3.3: Deterministic video style/angle variation via ``select_video_variation()``.
- FR-3.4: Video requests include component specs for overlays.
- FR-3.5: All prompts include ML compliance directives.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from orchestrator.core.config import get_settings
from orchestrator.core.database import async_session_factory
from orchestrator.core.exceptions import MediaGenerationError
from orchestrator.models.creative_asset import CreativeAsset
from orchestrator.schemas.media import (
    ImageGenerationRequest,
    ImageStyle,
    MediaAsset,
    VideoGenerationRequest,
)
from orchestrator.services.creative_asset_repository import CreativeAssetRepository
from orchestrator.services.gemini_media import GeminiMediaService
from orchestrator.services.media_compliance import MediaComplianceValidator
from orchestrator.services.prompt_engine import PromptEngine

if TYPE_CHECKING:
    from orchestrator.graph.state import GraphState

logger = logging.getLogger(__name__)

# Component roles extracted from serialised TowerBuild dicts.
_COMPONENT_ROLES: tuple[str, ...] = (
    "cpu",
    "motherboard",
    "ram",
    "gpu",
    "ssd",
    "psu",
    "case",
)


# ---------------------------------------------------------------------------
# Public node function
# ---------------------------------------------------------------------------


async def creative_director_node(state: GraphState) -> dict[str, object]:
    """LangGraph node: Creative Director (Agent 3). FR-3.1-FR-3.5.

    For each completed tower build, generates 4 images (FR-3.1) and
    1 video (FR-3.2), validates MercadoLibre compliance (FR-3.5), and
    persists asset metadata to the Local Registry.

    Args:
        state: Current graph state with ``completed_builds`` from Agent 1
            and ``completed_bundles`` from Agent 2.

    Returns:
        State update dict with ``completed_assets``, ``errors``, and
        ``run_status``.
    """
    if not state.completed_builds:
        logger.info("No completed_builds in state; returning empty assets.")
        return {
            "completed_assets": [],
            "errors": [],
            "run_status": "completed",
        }

    settings = get_settings()
    prompt_engine = PromptEngine()
    media_service = GeminiMediaService(settings, prompt_engine)
    compliance_validator = MediaComplianceValidator()

    errors: list[str] = []
    completed_assets: list[dict[str, object]] = []

    async with async_session_factory() as session:
        asset_repo = CreativeAssetRepository(session)

        for build in state.completed_builds:
            tier = str(build.get("tier", ""))
            tower_hash = str(build.get("bundle_hash", ""))
            case_name = _extract_case_name(build)
            component_summary = _build_component_summary(build)
            spec_list = _build_component_specs_list(build)

            # Find matching bundle for bundle_id linkage.
            matching_bundle = _find_matching_bundle(build, state.completed_bundles)
            bundle_id = str(matching_bundle.get("bundle_id", "")) if matching_bundle else None

            # Build image generation request for all 4 styles.
            image_request = ImageGenerationRequest(
                product_sku=tower_hash,
                case_name=case_name,
                component_summary=component_summary,
                tier=tier,
            )

            # FR-3.1: Generate 4 images (one per ImageStyle).
            images: list[MediaAsset] = []
            for idx in range(len(list(ImageStyle))):
                try:
                    asset = await media_service.generate_image(image_request, idx)
                    images.append(asset)
                except MediaGenerationError as exc:
                    _append_build_error(
                        errors,
                        tier,
                        f"Image generation failed (style {idx}): {exc.message}",
                    )

            # FR-3.3: Deterministic video style/angle variation.
            video_style, camera_angle = prompt_engine.select_video_variation(tower_hash)

            # FR-3.4: Video request includes component spec overlays.
            video_request = VideoGenerationRequest(
                product_sku=tower_hash,
                case_name=case_name,
                component_summary=component_summary,
                tier=tier,
                style=video_style,
                camera_angle=camera_angle,
                include_spec_overlays=True,
                spec_overlay_texts=spec_list,
            )

            # FR-3.2: Generate 1 video per build.
            video: MediaAsset | None = None
            try:
                video = await media_service.generate_video(video_request)
            except MediaGenerationError as exc:
                _append_build_error(errors, tier, f"Video generation failed: {exc.message}")

            # FR-3.5: Compliance validation on all generated assets.
            compliance_result = compliance_validator.validate_all(images, video)
            if not compliance_result.is_compliant:
                for violation in compliance_result.violations:
                    _append_build_error(
                        errors,
                        tier,
                        f"Compliance violation: {violation}",
                    )

            # Persist assets via CreativeAssetRepository.
            all_media: list[MediaAsset] = [
                *images,
                *([video] if video else []),
            ]
            db_assets: list[CreativeAsset] = []
            for asset in all_media:
                db_asset = CreativeAsset(
                    tower_hash=tower_hash,
                    bundle_id=bundle_id,
                    media_type=asset.media_type.value,
                    url=asset.url,
                    mime_type=asset.mime_type or "",
                    width=asset.width or 0,
                    height=asset.height or 0,
                    duration_seconds=asset.duration,
                    style=str(asset.style.value),
                    prompt_used=asset.prompt or "",
                )
                db_assets.append(db_asset)

            if db_assets:
                await asset_repo.create_many(db_assets)

            # Append serialised assets to the result list.
            for asset in all_media:
                completed_assets.append(asset.model_dump())

            logger.info(
                "Tier '%s': Generated %d images and %d video(s).",
                tier,
                len(images),
                1 if video else 0,
            )

        await session.commit()

    run_status: Literal["pending", "running", "completed", "failed"] = (
        "completed" if completed_assets else "failed"
    )
    return {
        "completed_assets": completed_assets,
        "errors": errors,
        "run_status": run_status,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_component_summary(build: dict[str, object]) -> str:
    """Build a brief text summary of key components in a tower build.

    Extracts the ``normalized_name`` from each component role and joins
    them into a comma-separated string suitable for prompt context.

    Args:
        build: Serialised ``TowerBuild`` dict from the Inventory Architect.

    Returns:
        Comma-separated string of component names, e.g.
        ``"Intel i7-13700K, ASUS ROG Strix Z790-E, ..."``.
    """
    names: list[str] = []
    for role in _COMPONENT_ROLES:
        component = build.get(role)
        if component and isinstance(component, dict):
            name = component.get("normalized_name", "")
            if name:
                names.append(str(name))
    # Include fans if present.
    fans = build.get("fans")
    if fans and isinstance(fans, list):
        for fan in fans:
            if isinstance(fan, dict):
                name = fan.get("normalized_name", "")
                if name:
                    names.append(str(name))
    return ", ".join(names)


def _build_component_specs_list(build: dict[str, object]) -> list[str]:
    """Build formatted spec strings for video overlay text (FR-3.4).

    Each string follows the format ``"ROLE: Component Name"`` and is
    intended for on-screen spec overlay display in generated videos.

    Args:
        build: Serialised ``TowerBuild`` dict.

    Returns:
        List of human-readable spec strings, e.g.
        ``["CPU: Intel i7-13700K", "RAM: Corsair 32 GB DDR5"]``.
    """
    specs: list[str] = []
    for role in _COMPONENT_ROLES:
        component = build.get(role)
        if component and isinstance(component, dict):
            name = component.get("normalized_name", "")
            if name:
                specs.append(f"{role.upper()}: {name}")
    return specs


def _find_matching_bundle(
    build: dict[str, object],
    bundles: list[dict[str, object]],
) -> dict[str, object] | None:
    """Find the bundle whose ``tower_hash`` matches a build's ``bundle_hash``.

    Args:
        build: Serialised ``TowerBuild`` dict.
        bundles: List of serialised ``BundleBuild`` dicts produced by the
            Bundle Creator node.

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


def _extract_case_name(build: dict[str, object]) -> str:
    """Extract the case component's normalised name from a build.

    Args:
        build: Serialised ``TowerBuild`` dict.

    Returns:
        The case's ``normalized_name``, or an empty string if unavailable.
    """
    case = build.get("case")
    if case and isinstance(case, dict):
        return str(case.get("normalized_name", ""))
    return ""


def _append_build_error(errors: list[str], tier: str, detail: str) -> None:
    """Append a formatted tier-scoped error message to the errors list.

    Args:
        errors: Mutable list of accumulated error strings.
        tier: The tier name that encountered the error.
        detail: The error detail message.
    """
    msg = f"Tier '{tier}': {detail}"
    errors.append(msg)
    logger.warning(msg)
