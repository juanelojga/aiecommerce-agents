"""Tests for the Creative Director LangGraph node.

Covers FR-3.1 through FR-3.5:

- FR-3.1: 4 images per build (one per ImageStyle).
- FR-3.2: 1 video per build.
- FR-3.3: Deterministic video style/angle variation via ``select_video_variation()``.
- FR-3.4: Video requests include component specs for overlays.
- FR-3.5: All prompts include ML compliance directives.
- Compliance validator runs on all assets.
- Assets persisted via ``CreativeAssetRepository``.
- API errors accumulated in ``errors`` list.
- Returns ``{"completed_assets": [...], "errors": [...], "run_status": "..."}``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.core.exceptions import MediaGenerationError
from orchestrator.graph.nodes.creative_director import (
    _build_component_specs_list,
    _build_component_summary,
    _extract_case_name,
    _find_matching_bundle,
    creative_director_node,
)
from orchestrator.graph.state import GraphState
from orchestrator.schemas.media import (
    ComplianceCheckResult,
    ImageStyle,
    MediaAsset,
    MediaType,
    VideoStyle,
)

# ---------------------------------------------------------------------------
# Test fixture helpers
# ---------------------------------------------------------------------------

_TOWER_HASH_A = "a" * 64
_TOWER_HASH_B = "b" * 64
_TOWER_HASH_C = "c" * 64


def _make_component(name: str, sku: str = "SKU-001", category: str = "cpu") -> dict[str, object]:
    """Build a minimal serialised ComponentSelection dict."""
    return {
        "sku": sku,
        "normalized_name": name,
        "category": category,
        "price": 100.0,
        "specs": {
            "id": 1,
            "code": "CODE-1",
            "sku": sku,
            "normalized_name": name,
            "price": 100.0,
            "category": category,
            "specs": {},
        },
    }


def _make_build(
    tier: str = "Home",
    bundle_hash: str = _TOWER_HASH_A,
    case_name: str = "NZXT H510",
) -> dict[str, object]:
    """Create a minimal serialised TowerBuild dict."""
    return {
        "tier": tier,
        "bundle_hash": bundle_hash,
        "total_price": 599.99,
        "cpu": _make_component("Intel Core i7-13700K", "CPU-001", "cpu"),
        "motherboard": _make_component("ASUS ROG Strix Z790-E", "MB-001", "motherboard"),
        "ram": _make_component("Corsair 32GB DDR5", "RAM-001", "ram"),
        "gpu": _make_component("RTX 4080", "GPU-001", "gpu"),
        "ssd": _make_component("Samsung 990 Pro 2TB", "SSD-001", "ssd"),
        "psu": _make_component("Corsair RM850x", "PSU-001", "psu"),
        "case": _make_component(case_name, "CASE-001", "case"),
        "fans": [_make_component("Noctua NF-A12x25", "FAN-001", "fan")],
    }


def _make_bundle(
    tower_hash: str = _TOWER_HASH_A,
    bundle_id: str = "bndl-001",
    tier: str = "Home",
) -> dict[str, object]:
    """Create a minimal serialised BundleBuild dict."""
    return {
        "tower_hash": tower_hash,
        "tier": tier,
        "peripheral_skus": ["KB-001", "MOUSE-001"],
        "bundle_id": bundle_id,
        "total_peripheral_price": 149.99,
    }


def _make_image_asset(
    style: ImageStyle = ImageStyle.FRONT_VIEW,
    asset_id: str = "img-001",
) -> MediaAsset:
    """Create a compliant MediaAsset representing a generated image."""
    return MediaAsset(
        asset_id=asset_id,
        media_type=MediaType.IMAGE,
        url="https://storage.example.com/image.png",
        style=style,
        width=1024,
        height=1024,
        mime_type="image/png",
        prompt="Generate a product photograph. No watermarks. No logos. "
        "No contact information. No promotional text overlays.",
    )


def _make_video_asset(
    style: VideoStyle = VideoStyle.TECH_SHOWCASE,
    asset_id: str = "vid-001",
) -> MediaAsset:
    """Create a compliant MediaAsset representing a generated video."""
    return MediaAsset(
        asset_id=asset_id,
        media_type=MediaType.VIDEO,
        url="https://storage.example.com/video.mp4",
        style=style,
        duration=5.0,
        width=1920,
        height=1080,
        mime_type="video/mp4",
        prompt="Create a 5-second product showcase video. No watermarks. "
        "No logos. No contact information. No promotional text overlays.",
    )


def _make_media_service_mock(
    images: list[MediaAsset] | None = None,
    video: MediaAsset | None = None,
    image_error: MediaGenerationError | None = None,
    video_error: MediaGenerationError | None = None,
) -> Any:
    """Return a mocked GeminiMediaService.

    Args:
        images: List of MediaAsset objects to return for each image call.
            Each call returns the next asset in order.
        video: MediaAsset to return for the video call.
        image_error: If set, raise this error on image generation calls.
        video_error: If set, raise this error on video generation calls.
    """
    mock = MagicMock()

    if image_error:
        mock.generate_image = AsyncMock(side_effect=image_error)
    elif images:
        mock.generate_image = AsyncMock(side_effect=images)
    else:
        default_images = [_make_image_asset(s, f"img-{i}") for i, s in enumerate(ImageStyle)]
        mock.generate_image = AsyncMock(side_effect=default_images)

    if video_error:
        mock.generate_video = AsyncMock(side_effect=video_error)
    elif video:
        mock.generate_video = AsyncMock(return_value=video)
    else:
        mock.generate_video = AsyncMock(return_value=_make_video_asset())

    return mock


def _configure_session_factory(mock_factory: Any) -> AsyncMock:
    """Configure the async_session_factory mock as an async context manager.

    Returns:
        The mock session object for further assertions.
    """
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_session


def _patch_node(
    media_service_mock: Any | None = None,
    asset_repo_mock: Any | None = None,
    compliance_result: ComplianceCheckResult | None = None,
) -> tuple[Any, ...]:
    """Build context manager patches for creative_director_node.

    Returns:
        Tuple of patch context managers.
    """
    if media_service_mock is None:
        media_service_mock = _make_media_service_mock()
    if asset_repo_mock is None:
        asset_repo_mock = AsyncMock()
        asset_repo_mock.create_many = AsyncMock(return_value=[])
    if compliance_result is None:
        compliance_result = ComplianceCheckResult(is_compliant=True, violations=[])

    compliance_mock = MagicMock()
    compliance_mock.validate_all = MagicMock(return_value=compliance_result)

    return (
        patch(
            "orchestrator.graph.nodes.creative_director.GeminiMediaService",
            return_value=media_service_mock,
        ),
        patch(
            "orchestrator.graph.nodes.creative_director.CreativeAssetRepository",
            return_value=asset_repo_mock,
        ),
        patch(
            "orchestrator.graph.nodes.creative_director.MediaComplianceValidator",
            return_value=compliance_mock,
        ),
        patch(
            "orchestrator.graph.nodes.creative_director.async_session_factory",
        ),
        media_service_mock,
        asset_repo_mock,
        compliance_mock,
    )


async def _run_node(
    state: GraphState,
    media_service_mock: Any | None = None,
    asset_repo_mock: Any | None = None,
    compliance_result: ComplianceCheckResult | None = None,
) -> tuple[dict[str, object], Any, Any, Any]:
    """Execute the creative_director_node with all dependencies mocked.

    Returns:
        Tuple of (result_dict, media_service_mock, asset_repo_mock, compliance_mock).
    """
    (
        media_svc_patch,
        repo_patch,
        compliance_patch,
        session_patch,
        media_svc,
        repo,
        compliance,
    ) = _patch_node(media_service_mock, asset_repo_mock, compliance_result)

    with media_svc_patch, repo_patch, compliance_patch, session_patch as mock_factory:
        _configure_session_factory(mock_factory)
        result = await creative_director_node(state)

    return result, media_svc, repo, compliance


# ---------------------------------------------------------------------------
# Unit tests: helper functions
# ---------------------------------------------------------------------------


class TestBuildComponentSummary:
    """Tests for _build_component_summary."""

    def test_includes_all_components(self) -> None:
        """Summary includes normalized names from all component roles."""
        build = _make_build()
        summary = _build_component_summary(build)
        assert "Intel Core i7-13700K" in summary
        assert "ASUS ROG Strix Z790-E" in summary
        assert "Corsair 32GB DDR5" in summary
        assert "RTX 4080" in summary
        assert "Samsung 990 Pro 2TB" in summary
        assert "Corsair RM850x" in summary
        assert "NZXT H510" in summary
        assert "Noctua NF-A12x25" in summary

    def test_empty_build(self) -> None:
        """Empty build returns empty summary."""
        summary = _build_component_summary({})
        assert summary == ""

    def test_missing_gpu(self) -> None:
        """Build without GPU omits GPU from summary."""
        build = _make_build()
        build["gpu"] = None
        summary = _build_component_summary(build)
        assert "RTX 4080" not in summary
        assert "Intel Core i7-13700K" in summary


class TestBuildComponentSpecsList:
    """Tests for _build_component_specs_list."""

    def test_formatted_spec_strings(self) -> None:
        """Each spec string uses the format 'ROLE: Component Name'."""
        build = _make_build()
        specs = _build_component_specs_list(build)
        assert "CPU: Intel Core i7-13700K" in specs
        assert "MOTHERBOARD: ASUS ROG Strix Z790-E" in specs
        assert "RAM: Corsair 32GB DDR5" in specs
        assert "GPU: RTX 4080" in specs
        assert "SSD: Samsung 990 Pro 2TB" in specs
        assert "PSU: Corsair RM850x" in specs
        assert "CASE: NZXT H510" in specs

    def test_empty_build(self) -> None:
        """Empty build returns empty spec list."""
        assert _build_component_specs_list({}) == []


class TestFindMatchingBundle:
    """Tests for _find_matching_bundle."""

    def test_correct_hash_matching(self) -> None:
        """Returns the bundle whose tower_hash matches the build's bundle_hash."""
        build = _make_build(bundle_hash=_TOWER_HASH_A)
        bundles = [
            _make_bundle(tower_hash=_TOWER_HASH_B, bundle_id="bndl-B"),
            _make_bundle(tower_hash=_TOWER_HASH_A, bundle_id="bndl-A"),
        ]
        result = _find_matching_bundle(build, bundles)
        assert result is not None
        assert result["bundle_id"] == "bndl-A"

    def test_no_match(self) -> None:
        """Returns None when no bundle matches."""
        build = _make_build(bundle_hash=_TOWER_HASH_C)
        bundles = [_make_bundle(tower_hash=_TOWER_HASH_A)]
        result = _find_matching_bundle(build, bundles)
        assert result is None

    def test_empty_bundles(self) -> None:
        """Returns None when bundles list is empty."""
        build = _make_build()
        assert _find_matching_bundle(build, []) is None

    def test_empty_hash(self) -> None:
        """Returns None when build has no bundle_hash."""
        build = _make_build()
        build["bundle_hash"] = ""
        assert _find_matching_bundle(build, [_make_bundle()]) is None


class TestExtractCaseName:
    """Tests for _extract_case_name."""

    def test_extracts_case_name(self) -> None:
        """Returns the case component's normalized_name."""
        build = _make_build(case_name="Fractal Design Meshify C")
        name = _extract_case_name(build)
        assert name == "Fractal Design Meshify C"

    def test_no_case(self) -> None:
        """Returns empty string when build has no case."""
        assert _extract_case_name({}) == ""

    def test_case_is_none(self) -> None:
        """Returns empty string when case is None."""
        build = _make_build()
        build["case"] = None
        assert _extract_case_name(build) == ""


# ---------------------------------------------------------------------------
# Integration tests: creative_director_node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_creative_director_empty_builds() -> None:
    """Empty completed_builds → empty completed_assets, completed status."""
    state = GraphState(completed_builds=[])
    result = await creative_director_node(state)

    assert result["completed_assets"] == []
    assert result["errors"] == []
    assert result["run_status"] == "completed"


@pytest.mark.asyncio
async def test_creative_director_single_build() -> None:
    """Single build generates 4 images + 1 video = 5 total assets."""
    state = GraphState(
        completed_builds=[_make_build()],
        completed_bundles=[_make_bundle()],
    )

    result, _, _, _ = await _run_node(state)

    assets: list[dict[str, object]] = result["completed_assets"]  # type: ignore[assignment]
    assert len(assets) == 5
    assert result["run_status"] == "completed"


@pytest.mark.asyncio
async def test_creative_director_multiple_tiers() -> None:
    """All tiers processed, each producing 5 assets."""
    builds = [
        _make_build("Home", _TOWER_HASH_A),
        _make_build("Business", _TOWER_HASH_B),
        _make_build("Gaming", _TOWER_HASH_C),
    ]
    bundles = [
        _make_bundle(_TOWER_HASH_A, "bndl-A", "Home"),
        _make_bundle(_TOWER_HASH_B, "bndl-B", "Business"),
        _make_bundle(_TOWER_HASH_C, "bndl-C", "Gaming"),
    ]

    # Need 4 images per build x 3 builds = 12 images, plus 3 videos
    all_images: list[MediaAsset] = []
    for build_idx in range(3):
        for i, s in enumerate(ImageStyle):
            all_images.append(_make_image_asset(s, f"img-{build_idx}-{i}"))
    all_videos = [_make_video_asset(asset_id=f"vid-{i}") for i in range(3)]

    media_mock = MagicMock()
    media_mock.generate_image = AsyncMock(side_effect=all_images)
    media_mock.generate_video = AsyncMock(side_effect=all_videos)

    state = GraphState(completed_builds=builds, completed_bundles=bundles)
    result, _, _, _ = await _run_node(state, media_service_mock=media_mock)

    assets: list[dict[str, object]] = result["completed_assets"]  # type: ignore[assignment]
    assert len(assets) == 15  # 5 per tier x 3 tiers
    assert result["run_status"] == "completed"
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_creative_director_images_count() -> None:
    """Exactly 4 images generated per build (FR-3.1)."""
    state = GraphState(
        completed_builds=[_make_build()],
        completed_bundles=[_make_bundle()],
    )

    result, media_svc, _, _ = await _run_node(state)

    assert media_svc.generate_image.call_count == 4
    assets: list[dict[str, object]] = result["completed_assets"]  # type: ignore[assignment]
    image_assets = [a for a in assets if a["media_type"] == "image"]
    assert len(image_assets) == 4


@pytest.mark.asyncio
async def test_creative_director_video_count() -> None:
    """Exactly 1 video generated per build (FR-3.2)."""
    state = GraphState(
        completed_builds=[_make_build()],
        completed_bundles=[_make_bundle()],
    )

    result, media_svc, _, _ = await _run_node(state)

    assert media_svc.generate_video.call_count == 1
    assets: list[dict[str, object]] = result["completed_assets"]  # type: ignore[assignment]
    video_assets = [a for a in assets if a["media_type"] == "video"]
    assert len(video_assets) == 1


@pytest.mark.asyncio
async def test_creative_director_compliance_pass() -> None:
    """Compliant assets succeed without adding compliance errors."""
    state = GraphState(
        completed_builds=[_make_build()],
        completed_bundles=[_make_bundle()],
    )
    compliance = ComplianceCheckResult(is_compliant=True, violations=[])

    result, _, _, _ = await _run_node(state, compliance_result=compliance)

    assert result["run_status"] == "completed"
    # No compliance-related errors
    error_list: list[str] = result["errors"]  # type: ignore[assignment]
    assert not any("Compliance" in e for e in error_list)


@pytest.mark.asyncio
async def test_creative_director_compliance_fail() -> None:
    """Non-compliant assets produce compliance error entries."""
    state = GraphState(
        completed_builds=[_make_build()],
        completed_bundles=[_make_bundle()],
    )
    compliance = ComplianceCheckResult(
        is_compliant=False,
        violations=["Image too small", "Missing prompt directive"],
    )

    result, _, _, _ = await _run_node(state, compliance_result=compliance)

    error_list: list[str] = result["errors"]  # type: ignore[assignment]
    compliance_errors = [e for e in error_list if "Compliance violation" in e]
    assert len(compliance_errors) == 2
    assert any("Image too small" in e for e in compliance_errors)
    assert any("Missing prompt directive" in e for e in compliance_errors)


@pytest.mark.asyncio
async def test_creative_director_api_error_handled() -> None:
    """API failure → error accumulated, no crash, run_status is failed."""
    state = GraphState(
        completed_builds=[_make_build()],
        completed_bundles=[_make_bundle()],
    )
    img_error = MediaGenerationError(
        "Imagen API error: quota exceeded",
        media_type="image",
        provider="gemini",
    )
    vid_error = MediaGenerationError(
        "Veo API error: timeout",
        media_type="video",
        provider="gemini",
    )
    media_mock = _make_media_service_mock(image_error=img_error, video_error=vid_error)

    result, _, _, _ = await _run_node(state, media_service_mock=media_mock)

    error_list: list[str] = result["errors"]  # type: ignore[assignment]
    assert len(error_list) >= 5  # 4 image errors + 1 video error
    assert result["run_status"] == "failed"
    # Ensure it didn't crash — we got a proper result dict
    assert "completed_assets" in result


@pytest.mark.asyncio
async def test_creative_director_persists_assets() -> None:
    """CreativeAssetRepository.create_many() is called with persisted assets."""
    state = GraphState(
        completed_builds=[_make_build()],
        completed_bundles=[_make_bundle()],
    )
    asset_repo_mock = AsyncMock()
    asset_repo_mock.create_many = AsyncMock(return_value=[])

    _result, _, repo, _ = await _run_node(state, asset_repo_mock=asset_repo_mock)

    repo.create_many.assert_called_once()
    persisted = repo.create_many.call_args[0][0]
    assert len(persisted) == 5  # 4 images + 1 video


@pytest.mark.asyncio
async def test_creative_director_no_matching_bundle() -> None:
    """When no bundle matches, tower-only assets are still generated."""
    state = GraphState(
        completed_builds=[_make_build(bundle_hash=_TOWER_HASH_A)],
        completed_bundles=[_make_bundle(tower_hash=_TOWER_HASH_B)],  # different hash
    )

    result, _, repo, _ = await _run_node(state)

    assets: list[dict[str, object]] = result["completed_assets"]  # type: ignore[assignment]
    assert len(assets) == 5
    assert result["run_status"] == "completed"

    # Persisted assets should have bundle_id=None
    persisted = repo.create_many.call_args[0][0]
    for db_asset in persisted:
        assert db_asset.bundle_id is None


@pytest.mark.asyncio
async def test_creative_director_spec_overlays() -> None:
    """Video generation request includes spec overlay texts (FR-3.4)."""
    state = GraphState(
        completed_builds=[_make_build()],
        completed_bundles=[_make_bundle()],
    )

    _result, media_svc, _, _ = await _run_node(state)

    # Verify the video request was built with spec overlays
    call_args = media_svc.generate_video.call_args
    video_request = call_args[0][0]
    assert video_request.include_spec_overlays is True
    assert len(video_request.spec_overlay_texts) > 0
    assert any("CPU:" in s for s in video_request.spec_overlay_texts)


@pytest.mark.asyncio
async def test_creative_director_visual_variation() -> None:
    """Different builds produce different video styles/angles (FR-3.3)."""
    builds = [
        _make_build("Home", _TOWER_HASH_A),
        _make_build("Gaming", _TOWER_HASH_B),
    ]
    bundles = [
        _make_bundle(_TOWER_HASH_A, "bndl-A"),
        _make_bundle(_TOWER_HASH_B, "bndl-B"),
    ]

    # 8 images total + 2 videos
    all_images = [
        _make_image_asset(s, f"img-{b}-{i}") for b in range(2) for i, s in enumerate(ImageStyle)
    ]
    all_videos = [_make_video_asset(asset_id=f"vid-{i}") for i in range(2)]

    media_mock = MagicMock()
    media_mock.generate_image = AsyncMock(side_effect=all_images)
    media_mock.generate_video = AsyncMock(side_effect=all_videos)

    state = GraphState(completed_builds=builds, completed_bundles=bundles)
    _result, _, _, _ = await _run_node(state, media_service_mock=media_mock)

    # Extract the video requests that were made
    video_calls = media_mock.generate_video.call_args_list
    assert len(video_calls) == 2

    req1 = video_calls[0][0][0]
    req2 = video_calls[1][0][0]

    # With different tower hashes, select_video_variation should produce
    # different style/angle pairs for at least one of the two dimensions.
    pair1 = (req1.style, req1.camera_angle)
    pair2 = (req2.style, req2.camera_angle)
    assert pair1 != pair2, (
        "Different tower hashes should produce different video style/angle variations"
    )
