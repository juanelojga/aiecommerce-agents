"""Tests for creative asset Pydantic schemas."""

from orchestrator.schemas.media import (
    CameraAngle,
    ComplianceCheckResult,
    CreativeResult,
    ImageGenerationRequest,
    ImageStyle,
    MediaAsset,
    MediaType,
    VideoGenerationRequest,
    VideoStyle,
)

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


def test_media_type_values() -> None:
    """MediaType enum has correct string values for image and video."""
    assert MediaType.IMAGE.value == "image"
    assert MediaType.VIDEO.value == "video"
    assert len(MediaType) == 2


def test_image_style_values() -> None:
    """All 4 image styles are present with the correct string values."""
    assert ImageStyle.FRONT_VIEW.value == "front_view"
    assert ImageStyle.THREE_QUARTER.value == "three_quarter"
    assert ImageStyle.DETAIL_CLOSEUP.value == "detail_closeup"
    assert ImageStyle.LIFESTYLE_CONTEXT.value == "lifestyle_context"
    assert len(ImageStyle) == 4


def test_video_style_values() -> None:
    """All video variation styles are present with the correct string values."""
    assert VideoStyle.DRAMATIC_LIGHTING.value == "dramatic_lighting"
    assert VideoStyle.SOFT_STUDIO.value == "soft_studio"
    assert VideoStyle.TECH_SHOWCASE.value == "tech_showcase"
    assert VideoStyle.MINIMALIST.value == "minimalist"
    assert len(VideoStyle) == 4


def test_camera_angle_values() -> None:
    """All camera angles are present with the correct string values."""
    assert CameraAngle.ORBIT.value == "orbit"
    assert CameraAngle.DOLLY_ZOOM.value == "dolly_zoom"
    assert CameraAngle.LOW_ANGLE.value == "low_angle"
    assert CameraAngle.TOP_DOWN.value == "top_down"
    assert len(CameraAngle) == 4


# ---------------------------------------------------------------------------
# MediaAsset
# ---------------------------------------------------------------------------


def test_media_asset_image() -> None:
    """MediaAsset correctly serializes an image asset."""
    asset = MediaAsset(
        asset_id="img-001",
        media_type=MediaType.IMAGE,
        url="https://cdn.example.com/img-001.png",
        style=ImageStyle.FRONT_VIEW,
    )

    assert asset.asset_id == "img-001"
    assert asset.media_type == MediaType.IMAGE
    assert asset.url == "https://cdn.example.com/img-001.png"
    assert asset.style == ImageStyle.FRONT_VIEW
    assert asset.duration is None

    data = asset.model_dump()
    assert data["media_type"] == "image"
    assert data["duration"] is None


def test_media_asset_video() -> None:
    """MediaAsset correctly serializes a video asset with duration."""
    asset = MediaAsset(
        asset_id="vid-001",
        media_type=MediaType.VIDEO,
        url="https://cdn.example.com/vid-001.mp4",
        style=VideoStyle.DRAMATIC_LIGHTING,
        duration=15.5,
    )

    assert asset.asset_id == "vid-001"
    assert asset.media_type == MediaType.VIDEO
    assert asset.duration == 15.5

    data = asset.model_dump()
    assert data["media_type"] == "video"
    assert data["duration"] == 15.5


# ---------------------------------------------------------------------------
# ImageGenerationRequest
# ---------------------------------------------------------------------------


def test_image_generation_request_defaults() -> None:
    """ImageGenerationRequest defaults styles to all 4 ImageStyle values."""
    request = ImageGenerationRequest(product_sku="GPU-001")

    assert request.product_sku == "GPU-001"
    assert len(request.styles) == 4
    assert ImageStyle.FRONT_VIEW in request.styles
    assert ImageStyle.THREE_QUARTER in request.styles
    assert ImageStyle.DETAIL_CLOSEUP in request.styles
    assert ImageStyle.LIFESTYLE_CONTEXT in request.styles


def test_image_generation_request_custom_styles() -> None:
    """ImageGenerationRequest accepts a custom subset of styles."""
    request = ImageGenerationRequest(
        product_sku="GPU-001",
        styles=[ImageStyle.FRONT_VIEW, ImageStyle.DETAIL_CLOSEUP],
    )

    assert len(request.styles) == 2
    assert ImageStyle.FRONT_VIEW in request.styles
    assert ImageStyle.DETAIL_CLOSEUP in request.styles


# ---------------------------------------------------------------------------
# VideoGenerationRequest
# ---------------------------------------------------------------------------


def test_video_generation_request_defaults() -> None:
    """VideoGenerationRequest defaults style to SOFT_STUDIO and angle to ORBIT."""
    request = VideoGenerationRequest(product_sku="GPU-001")

    assert request.product_sku == "GPU-001"
    assert request.style == VideoStyle.SOFT_STUDIO
    assert request.camera_angle == CameraAngle.ORBIT
    assert request.include_spec_overlays is False
    assert request.spec_overlay_texts == []


def test_video_generation_request_with_overlays() -> None:
    """VideoGenerationRequest correctly stores spec overlay fields."""
    request = VideoGenerationRequest(
        product_sku="GPU-001",
        style=VideoStyle.TECH_SHOWCASE,
        camera_angle=CameraAngle.DOLLY_ZOOM,
        include_spec_overlays=True,
        spec_overlay_texts=["16 GB VRAM", "PCIe 4.0"],
    )

    assert request.style == VideoStyle.TECH_SHOWCASE
    assert request.camera_angle == CameraAngle.DOLLY_ZOOM
    assert request.include_spec_overlays is True
    assert request.spec_overlay_texts == ["16 GB VRAM", "PCIe 4.0"]


# ---------------------------------------------------------------------------
# CreativeResult
# ---------------------------------------------------------------------------


def test_creative_result_serialization() -> None:
    """CreativeResult round-trips correctly through model_dump and model_validate."""
    image = MediaAsset(
        asset_id="img-001",
        media_type=MediaType.IMAGE,
        url="https://cdn.example.com/img-001.png",
        style=ImageStyle.FRONT_VIEW,
    )
    video = MediaAsset(
        asset_id="vid-001",
        media_type=MediaType.VIDEO,
        url="https://cdn.example.com/vid-001.mp4",
        style=VideoStyle.SOFT_STUDIO,
        duration=20.0,
    )
    compliance = ComplianceCheckResult(is_compliant=True, violations=[])
    result = CreativeResult(
        product_sku="GPU-001",
        images=[image],
        video=video,
        compliance=compliance,
    )

    data = result.model_dump()
    restored = CreativeResult.model_validate(data)

    assert restored.product_sku == "GPU-001"
    assert len(restored.images) == 1
    assert restored.images[0].asset_id == "img-001"
    assert restored.video is not None
    assert restored.video.duration == 20.0
    assert restored.compliance is not None
    assert restored.compliance.is_compliant is True


def test_creative_result_defaults() -> None:
    """CreativeResult defaults images to empty list, video and compliance to None."""
    result = CreativeResult(product_sku="CPU-001")

    assert result.images == []
    assert result.video is None
    assert result.compliance is None


# ---------------------------------------------------------------------------
# ComplianceCheckResult
# ---------------------------------------------------------------------------


def test_compliance_check_result_defaults() -> None:
    """ComplianceCheckResult defaults to compliant=True with empty violations."""
    check = ComplianceCheckResult()

    assert check.is_compliant is True
    assert check.violations == []


def test_compliance_check_result_with_violations() -> None:
    """ComplianceCheckResult correctly stores violations when not compliant."""
    check = ComplianceCheckResult(
        is_compliant=False,
        violations=["Brand logo missing", "Resolution too low"],
    )

    assert check.is_compliant is False
    assert len(check.violations) == 2
    assert "Brand logo missing" in check.violations
