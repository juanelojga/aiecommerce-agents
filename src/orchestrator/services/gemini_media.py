"""Google Gemini media generation service.

Implements ``MediaGeneratorProtocol`` using the ``google-genai`` SDK to
generate product images via Imagen and product videos via Veo.  Includes
error handling, configurable timeouts, and retry logic delegated to the
SDK's built-in ``HttpOptions``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

from google import genai
from google.genai import types

from orchestrator.core.exceptions import MediaGenerationError
from orchestrator.schemas.media import (
    MediaAsset,
    MediaType,
)
from orchestrator.services.prompt_engine import PromptEngine

if TYPE_CHECKING:
    from orchestrator.core.config import Settings
    from orchestrator.schemas.media import ImageGenerationRequest, VideoGenerationRequest

logger = logging.getLogger(__name__)

_PROVIDER = "gemini"


class GeminiMediaService:
    """Gemini API client for image and video generation.

    Uses Imagen for images and Veo for videos.  Satisfies
    ``MediaGeneratorProtocol`` via structural sub-typing (no explicit
    inheritance required).

    Args:
        settings: Application settings containing API keys and model names.
        prompt_engine: Optional prompt builder; a default ``PromptEngine``
            is created when ``None``.
    """

    def __init__(
        self,
        settings: Settings,
        prompt_engine: PromptEngine | None = None,
    ) -> None:
        """Initialise the Gemini media service.

        Args:
            settings: Application settings with API key and model config.
            prompt_engine: Prompt builder instance; defaults to a new
                ``PromptEngine`` when not supplied.
        """
        self._client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self._image_model = settings.GEMINI_IMAGE_MODEL
        self._video_model = settings.GEMINI_VIDEO_MODEL
        self._timeout = settings.MEDIA_GENERATION_TIMEOUT
        self._prompt_engine = prompt_engine or PromptEngine()

    # ------------------------------------------------------------------
    # Image generation (Imagen)
    # ------------------------------------------------------------------

    async def generate_image(
        self,
        request: ImageGenerationRequest,
        style_index: int,
    ) -> MediaAsset:
        """Generate a single product image for the given style index.

        Args:
            request: Parameters describing the product and desired styles.
            style_index: Index into ``request.styles`` selecting the style.

        Returns:
            A ``MediaAsset`` representing the generated image.

        Raises:
            MediaGenerationError: If the Imagen API call fails or returns
                no images.
        """
        style = request.styles[style_index]
        prompt = self._prompt_engine.build_image_prompt(request, style)

        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_images(
                    model=self._image_model,
                    prompt=prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        http_options=types.HttpOptions(timeout=self._timeout),
                    ),
                ),
                timeout=self._timeout,
            )
        except TimeoutError as exc:
            raise MediaGenerationError(
                f"Image generation timed out after {self._timeout}s",
                media_type="image",
                provider=_PROVIDER,
            ) from exc
        except Exception as exc:
            raise MediaGenerationError(
                f"Imagen API error: {exc}",
                media_type="image",
                provider=_PROVIDER,
            ) from exc

        if not response.generated_images:
            raise MediaGenerationError(
                "Imagen API returned no images",
                media_type="image",
                provider=_PROVIDER,
            )

        generated = response.generated_images[0]
        image = generated.image
        url = (image.gcs_uri or "") if image else ""
        mime_type = image.mime_type if image else None

        return MediaAsset(
            asset_id=str(uuid.uuid4()),
            media_type=MediaType.IMAGE,
            url=url,
            style=style,
            mime_type=mime_type,
            prompt=prompt,
        )

    # ------------------------------------------------------------------
    # Video generation (Veo)
    # ------------------------------------------------------------------

    async def generate_video(
        self,
        request: VideoGenerationRequest,
    ) -> MediaAsset:
        """Generate a product video using Veo.

        Args:
            request: Parameters describing the product and desired video
                style.

        Returns:
            A ``MediaAsset`` representing the generated video.

        Raises:
            MediaGenerationError: If the Veo API call fails or returns
                no video.
        """
        prompt = self._prompt_engine.build_video_prompt(request)

        try:
            operation = await asyncio.wait_for(
                self._client.aio.models.generate_videos(
                    model=self._video_model,
                    prompt=prompt,
                    config=types.GenerateVideosConfig(
                        http_options=types.HttpOptions(timeout=self._timeout),
                    ),
                ),
                timeout=self._timeout,
            )
        except TimeoutError as exc:
            raise MediaGenerationError(
                f"Video generation timed out after {self._timeout}s",
                media_type="video",
                provider=_PROVIDER,
            ) from exc
        except Exception as exc:
            raise MediaGenerationError(
                f"Veo API error: {exc}",
                media_type="video",
                provider=_PROVIDER,
            ) from exc

        result = operation.result
        if not result or not result.generated_videos:
            raise MediaGenerationError(
                "Veo API returned no videos",
                media_type="video",
                provider=_PROVIDER,
            )

        generated = result.generated_videos[0]
        video = generated.video
        url = (video.uri or "") if video else ""
        mime_type = video.mime_type if video else None

        return MediaAsset(
            asset_id=str(uuid.uuid4()),
            media_type=MediaType.VIDEO,
            url=url,
            style=request.style,
            mime_type=mime_type,
            prompt=prompt,
        )

    # ------------------------------------------------------------------
    # Batch image generation (FR-3.1)
    # ------------------------------------------------------------------

    async def generate_all_images(
        self,
        request: ImageGenerationRequest,
    ) -> list[MediaAsset]:
        """Generate images for all styles in the request (exactly 4 by default).

        Generates one image per style listed in ``request.styles``,
        producing exactly 4 assets when the default style list is used
        (FR-3.1).

        Args:
            request: Image generation request with styles to iterate over.

        Returns:
            List of ``MediaAsset`` objects, one per style.

        Raises:
            MediaGenerationError: If any individual generation fails.
        """
        assets: list[MediaAsset] = []
        for idx in range(len(request.styles)):
            asset = await self.generate_image(request, idx)
            assets.append(asset)
        return assets
