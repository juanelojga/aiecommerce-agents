#!/usr/bin/env python3
"""Step 4 — Creative Asset Generation (Creative Director).

For each completed tower build + bundle:
  1. Constructs image and video generation requests.
  2. Generates 4 images (one per style) + 1 video via Gemini API.
  3. Validates compliance against MercadoLibre rules.
  4. Persists asset metadata to the ``creative_assets`` table.

Supports ``--dry-run`` to preview prompts without calling Gemini (saves API costs).

Visible output:
  - Per-build prompts (in dry-run) or generated asset URLs.
  - Compliance validation results.

Usage:
    uv run python scripts/test_step4_creative_assets.py --dry-run
    uv run python scripts/test_step4_creative_assets.py
    uv run python scripts/test_step4_creative_assets.py --tiers Home
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
    print_warning,
    save_step_output,
)

# Component roles used by the Creative Director node.
_COMPONENT_ROLES = ("cpu", "motherboard", "ram", "gpu", "ssd", "psu", "case")


def _build_component_summary(build: dict[str, object]) -> str:
    """Build a summary string from component names in a tower build.

    Args:
        build: Serialised TowerBuild dict.

    Returns:
        Comma-separated component names.
    """
    names: list[str] = []
    for role in _COMPONENT_ROLES:
        component = build.get(role)
        if component and isinstance(component, dict):
            name = component.get("normalized_name", "")
            if name:
                names.append(str(name))
    fans = build.get("fans")
    if fans and isinstance(fans, list):
        for fan in fans:
            if isinstance(fan, dict):
                name = fan.get("normalized_name", "")
                if name:
                    names.append(str(name))
    return ", ".join(names)


def _build_spec_list(build: dict[str, object]) -> list[str]:
    """Build spec overlay text lines for video generation.

    Args:
        build: Serialised TowerBuild dict.

    Returns:
        List of ``"ROLE: Name"`` strings.
    """
    specs: list[str] = []
    for role in _COMPONENT_ROLES:
        component = build.get(role)
        if component and isinstance(component, dict):
            name = component.get("normalized_name", "")
            if name:
                specs.append(f"{role.upper()}: {name}")
    return specs


def _extract_case_name(build: dict[str, object]) -> str:
    """Extract the case name from a build dict.

    Args:
        build: Serialised TowerBuild dict.

    Returns:
        Case component name or empty string.
    """
    case = build.get("case")
    if case and isinstance(case, dict):
        return str(case.get("normalized_name", ""))
    return ""


async def main() -> None:
    """Run creative asset generation for each build."""
    parser = build_base_parser("Step 4 — Creative Asset Generation (Creative Director)")
    args = parser.parse_args()

    print_header("Step 4 — Creative Asset Generation (Creative Director)")

    # Load builds + bundles from previous steps
    print_info("Loading data from Step 3 output...")
    bundle_data = load_step_output("step3_bundles.json")
    completed_builds: list[dict[str, object]] = bundle_data.get("completed_builds", [])
    completed_bundles: list[dict[str, object]] = bundle_data.get("completed_bundles", [])

    if not completed_builds:
        print_error("No completed builds found in Step 3 output.")
        sys.exit(1)

    # Filter to requested tiers
    builds_to_process = [b for b in completed_builds if str(b.get("tier", "")) in args.tiers]
    print_success(f"Loaded {len(builds_to_process)} build(s), {len(completed_bundles)} bundle(s)")

    if args.dry_run:
        print_warning("DRY RUN — prompts will be generated but Gemini API will NOT be called")

    from orchestrator.schemas.media import (
        ImageGenerationRequest,
        ImageStyle,
        MediaAsset,
        VideoGenerationRequest,
    )
    from orchestrator.services.prompt_engine import PromptEngine

    prompt_engine = PromptEngine()
    completed_assets: list[dict[str, object]] = []
    error_count = 0

    for build in builds_to_process:
        tier = str(build.get("tier", ""))
        tower_hash = str(build.get("bundle_hash", ""))
        case_name = _extract_case_name(build)
        component_summary = _build_component_summary(build)
        spec_list = _build_spec_list(build)

        print_subheader(f"Tier: {tier} (Tower: {tower_hash[:16]}...)")
        print_key_value("Case", case_name)
        print_key_value("Components", component_summary[:80] + "...")

        # Build image request
        image_request = ImageGenerationRequest(
            product_sku=tower_hash,
            case_name=case_name,
            component_summary=component_summary,
            tier=tier,
        )

        # Show image prompts
        print_subheader(f"Image Prompts ({len(list(ImageStyle))} styles)")
        prompt_rows: list[list[str]] = []
        for style in ImageStyle:
            prompt = prompt_engine.build_image_prompt(image_request, style)
            prompt_rows.append([style.value, prompt[:80] + "..."])
        print_table(["Style", "Prompt Preview"], prompt_rows)

        # Video prompt
        video_style, camera_angle = prompt_engine.select_video_variation(tower_hash)
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
        video_prompt = prompt_engine.build_video_prompt(video_request)

        print_subheader("Video Prompt")
        print_key_value("Style", video_style.value)
        print_key_value("Camera Angle", camera_angle.value)
        print_info(f"Prompt: {video_prompt[:120]}...")

        if args.dry_run:
            print_success("DRY RUN — Skipping Gemini API call")
            # Create placeholder asset records for output continuity
            for i, style in enumerate(ImageStyle):
                completed_assets.append(
                    {
                        "asset_id": f"dry-run-img-{tower_hash[:8]}-{i}",
                        "media_type": "image",
                        "url": f"https://placeholder.test/image-{style.value}.png",
                        "style": style.value,
                        "mime_type": "image/png",
                        "width": 1024,
                        "height": 1024,
                        "prompt": prompt_engine.build_image_prompt(image_request, style),
                    }
                )
            completed_assets.append(
                {
                    "asset_id": f"dry-run-vid-{tower_hash[:8]}",
                    "media_type": "video",
                    "url": f"https://placeholder.test/video-{video_style.value}.mp4",
                    "style": video_style.value,
                    "duration": 10.0,
                    "width": 1920,
                    "height": 1080,
                    "mime_type": "video/mp4",
                    "prompt": video_prompt,
                }
            )
            continue

        # Real API calls
        from orchestrator.core.config import get_settings
        from orchestrator.core.database import async_session_factory, create_tables
        from orchestrator.models.creative_asset import CreativeAsset
        from orchestrator.services.creative_asset_repository import CreativeAssetRepository
        from orchestrator.services.gemini_media import GeminiMediaService
        from orchestrator.services.media_compliance import MediaComplianceValidator

        settings = get_settings()
        media_service = GeminiMediaService(settings, prompt_engine)
        compliance_validator = MediaComplianceValidator()

        await create_tables()

        images: list[MediaAsset] = []
        for idx in range(len(image_request.styles)):
            try:
                asset = await media_service.generate_image(image_request, idx)
                images.append(asset)
                print_success(f"Image {idx + 1} generated: {asset.url[:60]}...")
            except Exception as exc:
                print_error(f"Image {idx + 1} failed: {exc}")
                error_count += 1

        video: MediaAsset | None = None
        try:
            video = await media_service.generate_video(video_request)
            print_success(f"Video generated: {video.url[:60]}...")
        except Exception as exc:
            print_error(f"Video generation failed: {exc}")
            error_count += 1

        # Compliance check
        compliance_result = compliance_validator.validate_all(images, video)
        if compliance_result.is_compliant:
            print_success("Compliance validation passed")
        else:
            for violation in compliance_result.violations:
                print_warning(f"Compliance: {violation}")

        # Show asset summary
        asset_rows: list[list[str]] = []
        all_media: list[MediaAsset] = [*images, *([video] if video else [])]
        for asset in all_media:
            asset_rows.append(
                [
                    asset.media_type.value.upper(),
                    str(asset.style.value),
                    asset.mime_type or "?",
                    f"{asset.width or '?'}x{asset.height or '?'}",
                    asset.url[:50] + "...",
                ]
            )
        print_table(["Type", "Style", "MIME", "Dimensions", "URL"], asset_rows)

        # Persist to database
        matching_bundle = next(
            (b for b in completed_bundles if str(b.get("tower_hash", "")) == tower_hash),
            None,
        )
        bundle_id = str(matching_bundle.get("bundle_id", "")) if matching_bundle else None

        async with async_session_factory() as session:
            asset_repo = CreativeAssetRepository(session)
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
                await session.commit()
                print_success(f"Persisted {len(db_assets)} asset(s) to database")

        for asset in all_media:
            completed_assets.append(asset.model_dump())

    # Save output
    print_subheader("Saving Output")
    save_step_output(
        "step4_assets.json",
        {
            "completed_assets": completed_assets,
            "completed_builds": completed_builds,
            "completed_bundles": completed_bundles,
        },
    )

    asset_count = len(completed_assets)
    print_step_summary("Step 4 — Creative Assets", asset_count, error_count)


if __name__ == "__main__":
    asyncio.run(main())
