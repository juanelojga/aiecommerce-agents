"""Tests for the Gemini media generation service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.core.config import Settings
from orchestrator.core.exceptions import MediaGenerationError
from orchestrator.schemas.media import (
    CameraAngle,
    ImageGenerationRequest,
    ImageStyle,
    MediaAsset,
    MediaType,
    VideoGenerationRequest,
    VideoStyle,
)
from orchestrator.services.gemini_media import GeminiMediaService
from orchestrator.services.prompt_engine import PromptEngine

if TYPE_CHECKING:
    from orchestrator.services.media_protocol import MediaGeneratorProtocol

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DB_URL = "sqlite+aiosqlite:///./test.db"


@pytest.fixture()
def settings() -> Settings:
    """Return settings with a test API key."""
    return Settings(
        DATABASE_URL=_DB_URL,
        GOOGLE_API_KEY="test-api-key",
        MEDIA_GENERATION_TIMEOUT=30,
    )


@pytest.fixture()
def prompt_engine() -> PromptEngine:
    """Return a real PromptEngine instance."""
    return PromptEngine()


@pytest.fixture()
def mock_prompt_engine() -> MagicMock:
    """Return a mock PromptEngine for verifying calls."""
    engine = MagicMock(spec=PromptEngine)
    engine.build_image_prompt.return_value = "mocked image prompt"
    engine.build_video_prompt.return_value = "mocked video prompt"
    return engine


def _make_image_request(**kwargs: object) -> ImageGenerationRequest:
    """Build an image generation request with defaults."""
    defaults: dict[str, object] = {
        "product_sku": "GPU-001",
        "case_name": "NZXT H510",
        "component_summary": "RTX 3080, Ryzen 5600X",
        "tier": "Gaming",
    }
    defaults.update(kwargs)
    return ImageGenerationRequest(**defaults)


def _make_video_request(**kwargs: object) -> VideoGenerationRequest:
    """Build a video generation request with defaults."""
    defaults: dict[str, object] = {
        "product_sku": "GPU-001",
        "case_name": "NZXT H510",
        "component_summary": "RTX 3080, Ryzen 5600X",
        "tier": "Gaming",
        "style": VideoStyle.TECH_SHOWCASE,
        "camera_angle": CameraAngle.ORBIT,
    }
    defaults.update(kwargs)
    return VideoGenerationRequest(**defaults)


def _mock_image_response(gcs_uri: str = "gs://bucket/img.png") -> MagicMock:
    """Build a mock Imagen API response with one generated image."""
    image = MagicMock()
    image.gcs_uri = gcs_uri
    image.mime_type = "image/png"

    generated_image = MagicMock()
    generated_image.image = image

    response = MagicMock()
    response.generated_images = [generated_image]
    return response


def _mock_video_operation(uri: str = "gs://bucket/vid.mp4") -> MagicMock:
    """Build a mock Veo operation that resolves to a video."""
    video = MagicMock()
    video.uri = uri
    video.mime_type = "video/mp4"

    generated_video = MagicMock()
    generated_video.video = video

    result_response = MagicMock()
    result_response.generated_videos = [generated_video]

    operation = MagicMock()
    operation.result = result_response
    return operation


# ---------------------------------------------------------------------------
# generate_image — success
# ---------------------------------------------------------------------------


class TestGenerateImageSuccess:
    """Test successful image generation."""

    @pytest.mark.asyncio
    async def test_generate_image_success(self, settings: Settings) -> None:
        """Successful Imagen API call returns a MediaAsset."""
        service = GeminiMediaService(settings)
        request = _make_image_request()
        mock_resp = _mock_image_response("gs://bucket/test-img.png")

        with patch.object(
            service._client.aio.models,
            "generate_images",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            asset = await service.generate_image(request, 0)

        assert isinstance(asset, MediaAsset)
        assert asset.media_type == MediaType.IMAGE
        assert asset.url == "gs://bucket/test-img.png"
        assert asset.style == ImageStyle.FRONT_VIEW
        assert asset.mime_type == "image/png"
        assert asset.prompt is not None


# ---------------------------------------------------------------------------
# generate_image — API error
# ---------------------------------------------------------------------------


class TestGenerateImageApiError:
    """Test image generation API failure."""

    @pytest.mark.asyncio
    async def test_generate_image_api_error(self, settings: Settings) -> None:
        """API failure raises MediaGenerationError."""
        service = GeminiMediaService(settings)
        request = _make_image_request()

        with (
            patch.object(
                service._client.aio.models,
                "generate_images",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API unavailable"),
            ),
            pytest.raises(MediaGenerationError, match="Imagen API error"),
        ):
            await service.generate_image(request, 0)


# ---------------------------------------------------------------------------
# generate_image — timeout
# ---------------------------------------------------------------------------


class TestGenerateImageTimeout:
    """Test image generation timeout handling."""

    @pytest.mark.asyncio
    async def test_generate_image_timeout(self, settings: Settings) -> None:
        """Timeout raises MediaGenerationError."""
        service = GeminiMediaService(settings)
        request = _make_image_request()

        with (
            patch.object(
                service._client.aio.models,
                "generate_images",
                new_callable=AsyncMock,
                side_effect=TimeoutError("timed out"),
            ),
            pytest.raises(MediaGenerationError, match="timed out"),
        ):
            await service.generate_image(request, 0)


# ---------------------------------------------------------------------------
# generate_image — uses PromptEngine
# ---------------------------------------------------------------------------


class TestGenerateImageUsesPromptEngine:
    """Test that PromptEngine is invoked for prompt construction."""

    @pytest.mark.asyncio
    async def test_generate_image_uses_prompt_engine(
        self,
        settings: Settings,
        mock_prompt_engine: MagicMock,
    ) -> None:
        """PromptEngine.build_image_prompt is called with the correct args."""
        service = GeminiMediaService(settings, prompt_engine=mock_prompt_engine)
        request = _make_image_request()
        mock_resp = _mock_image_response()

        with patch.object(
            service._client.aio.models,
            "generate_images",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            asset = await service.generate_image(request, 0)

        mock_prompt_engine.build_image_prompt.assert_called_once_with(
            request, ImageStyle.FRONT_VIEW
        )
        assert asset.prompt == "mocked image prompt"


# ---------------------------------------------------------------------------
# generate_video — success
# ---------------------------------------------------------------------------


class TestGenerateVideoSuccess:
    """Test successful video generation."""

    @pytest.mark.asyncio
    async def test_generate_video_success(self, settings: Settings) -> None:
        """Successful Veo API call returns a MediaAsset."""
        service = GeminiMediaService(settings)
        request = _make_video_request()
        mock_op = _mock_video_operation("gs://bucket/test-vid.mp4")

        with patch.object(
            service._client.aio.models,
            "generate_videos",
            new_callable=AsyncMock,
            return_value=mock_op,
        ):
            asset = await service.generate_video(request)

        assert isinstance(asset, MediaAsset)
        assert asset.media_type == MediaType.VIDEO
        assert asset.url == "gs://bucket/test-vid.mp4"
        assert asset.style == VideoStyle.TECH_SHOWCASE
        assert asset.mime_type == "video/mp4"
        assert asset.prompt is not None


# ---------------------------------------------------------------------------
# generate_video — API error
# ---------------------------------------------------------------------------


class TestGenerateVideoApiError:
    """Test video generation API failure."""

    @pytest.mark.asyncio
    async def test_generate_video_api_error(self, settings: Settings) -> None:
        """API failure raises MediaGenerationError."""
        service = GeminiMediaService(settings)
        request = _make_video_request()

        with (
            patch.object(
                service._client.aio.models,
                "generate_videos",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Veo down"),
            ),
            pytest.raises(MediaGenerationError, match="Veo API error"),
        ):
            await service.generate_video(request)


# ---------------------------------------------------------------------------
# generate_video — spec overlays
# ---------------------------------------------------------------------------


class TestGenerateVideoSpecOverlays:
    """Test that spec overlays are included in the video prompt."""

    @pytest.mark.asyncio
    async def test_generate_video_includes_spec_overlays(
        self,
        settings: Settings,
    ) -> None:
        """Video prompt includes spec overlay texts when enabled."""
        service = GeminiMediaService(settings)
        request = _make_video_request(
            include_spec_overlays=True,
            spec_overlay_texts=["CPU: Ryzen 5600X", "GPU: RTX 3080"],
        )
        mock_op = _mock_video_operation()

        with patch.object(
            service._client.aio.models,
            "generate_videos",
            new_callable=AsyncMock,
            return_value=mock_op,
        ):
            asset = await service.generate_video(request)

        assert asset.prompt is not None
        assert "CPU: Ryzen 5600X" in asset.prompt
        assert "GPU: RTX 3080" in asset.prompt


# ---------------------------------------------------------------------------
# generate_all_images — returns four
# ---------------------------------------------------------------------------


class TestGenerateAllImagesReturnsFour:
    """Test that generate_all_images produces exactly 4 assets."""

    @pytest.mark.asyncio
    async def test_generate_all_images_returns_four(self, settings: Settings) -> None:
        """Default request produces exactly 4 MediaAsset objects."""
        service = GeminiMediaService(settings)
        request = _make_image_request()

        with patch.object(
            service._client.aio.models,
            "generate_images",
            new_callable=AsyncMock,
            return_value=_mock_image_response(),
        ):
            assets = await service.generate_all_images(request)

        assert len(assets) == 4
        assert all(isinstance(a, MediaAsset) for a in assets)


# ---------------------------------------------------------------------------
# generate_all_images — different styles
# ---------------------------------------------------------------------------


class TestGenerateAllImagesDifferentStyles:
    """Test that generate_all_images uses distinct styles for each image."""

    @pytest.mark.asyncio
    async def test_generate_all_images_different_styles(self, settings: Settings) -> None:
        """Each generated asset uses a different ImageStyle."""
        service = GeminiMediaService(settings)
        request = _make_image_request()

        with patch.object(
            service._client.aio.models,
            "generate_images",
            new_callable=AsyncMock,
            return_value=_mock_image_response(),
        ):
            assets = await service.generate_all_images(request)

        styles = [a.style for a in assets]
        assert len(set(styles)) == 4
        for image_style in ImageStyle:
            assert image_style in styles


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    """Test that GeminiMediaService satisfies MediaGeneratorProtocol."""

    def test_satisfies_media_generator_protocol(self, settings: Settings) -> None:
        """GeminiMediaService is assignable to MediaGeneratorProtocol."""
        service = GeminiMediaService(settings)
        generator: MediaGeneratorProtocol = service
        assert generator is service
