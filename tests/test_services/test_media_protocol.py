"""Tests for the media generation protocol definitions."""

import pytest

from orchestrator.schemas.media import (
    CameraAngle,
    ImageGenerationRequest,
    ImageStyle,
    MediaAsset,
    MediaType,
    VideoGenerationRequest,
    VideoStyle,
)
from orchestrator.services.media_protocol import (
    ImageGeneratorProtocol,
    MediaGeneratorProtocol,
    VideoGeneratorProtocol,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IMAGE_ASSET = MediaAsset(
    asset_id="img-001",
    media_type=MediaType.IMAGE,
    url="https://cdn.example.com/img-001.png",
    style=ImageStyle.FRONT_VIEW,
)

_VIDEO_ASSET = MediaAsset(
    asset_id="vid-001",
    media_type=MediaType.VIDEO,
    url="https://cdn.example.com/vid-001.mp4",
    style=VideoStyle.SOFT_STUDIO,
    duration=15.0,
)


# ---------------------------------------------------------------------------
# Protocol identity
# ---------------------------------------------------------------------------


def test_protocol_is_typing_protocol() -> None:
    """All three protocol classes must be genuine ``typing.Protocol`` subclasses."""
    for proto in (ImageGeneratorProtocol, VideoGeneratorProtocol, MediaGeneratorProtocol):
        assert getattr(proto, "_is_protocol", False), f"{proto.__name__} is not a typing.Protocol"


# ---------------------------------------------------------------------------
# Mock satisfies combined protocol
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_implementation_satisfies_protocol() -> None:
    """A mock class implementing both methods satisfies ``MediaGeneratorProtocol``."""

    class MockMediaGenerator:
        async def generate_image(
            self, request: ImageGenerationRequest, style_index: int
        ) -> MediaAsset:
            return _IMAGE_ASSET

        async def generate_video(self, request: VideoGenerationRequest) -> MediaAsset:
            return _VIDEO_ASSET

    generator: MediaGeneratorProtocol = MockMediaGenerator()

    image_request = ImageGenerationRequest(product_sku="GPU-001")
    video_request = VideoGenerationRequest(product_sku="GPU-001")

    image = await generator.generate_image(image_request, 0)
    video = await generator.generate_video(video_request)

    assert image.media_type == MediaType.IMAGE
    assert video.media_type == MediaType.VIDEO


# ---------------------------------------------------------------------------
# ImageGeneratorProtocol — standalone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_image_generator_protocol_independent() -> None:
    """A class implementing only ``generate_image`` satisfies ``ImageGeneratorProtocol``."""

    class MockImageGenerator:
        async def generate_image(
            self, request: ImageGenerationRequest, style_index: int
        ) -> MediaAsset:
            return _IMAGE_ASSET

    generator: ImageGeneratorProtocol = MockImageGenerator()

    request = ImageGenerationRequest(
        product_sku="GPU-001",
        styles=[ImageStyle.FRONT_VIEW, ImageStyle.DETAIL_CLOSEUP],
    )
    asset = await generator.generate_image(request, 1)

    assert asset is _IMAGE_ASSET
    assert asset.media_type == MediaType.IMAGE


# ---------------------------------------------------------------------------
# VideoGeneratorProtocol — standalone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_video_generator_protocol_independent() -> None:
    """A class implementing only ``generate_video`` satisfies ``VideoGeneratorProtocol``."""

    class MockVideoGenerator:
        async def generate_video(self, request: VideoGenerationRequest) -> MediaAsset:
            return _VIDEO_ASSET

    generator: VideoGeneratorProtocol = MockVideoGenerator()

    request = VideoGenerationRequest(
        product_sku="GPU-001",
        style=VideoStyle.TECH_SHOWCASE,
        camera_angle=CameraAngle.DOLLY_ZOOM,
    )
    asset = await generator.generate_video(request)

    assert asset is _VIDEO_ASSET
    assert asset.media_type == MediaType.VIDEO
