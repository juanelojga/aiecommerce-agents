"""Protocol definitions for media generation services.

Defines ``ImageGeneratorProtocol``, ``VideoGeneratorProtocol``, and the combined
``MediaGeneratorProtocol`` using ``typing.Protocol`` so that any provider
implementation can be swapped without changing business logic (DIP).
"""

from typing import Protocol

from orchestrator.schemas.media import ImageGenerationRequest, MediaAsset, VideoGenerationRequest


class ImageGeneratorProtocol(Protocol):
    """Protocol for services that generate product images.

    Any class that implements ``generate_image`` with the correct signature
    satisfies this protocol without explicit inheritance.
    """

    async def generate_image(self, request: ImageGenerationRequest, style_index: int) -> MediaAsset:
        """Generate a single product image for the given style index.

        Args:
            request: Parameters describing the product and desired styles.
            style_index: Index into ``request.styles`` that selects the style
                to generate.

        Returns:
            A :class:`~orchestrator.schemas.media.MediaAsset` representing the
            generated image.
        """
        ...


class VideoGeneratorProtocol(Protocol):
    """Protocol for services that generate product videos.

    Any class that implements ``generate_video`` with the correct signature
    satisfies this protocol without explicit inheritance.
    """

    async def generate_video(self, request: VideoGenerationRequest) -> MediaAsset:
        """Generate a product video.

        Args:
            request: Parameters describing the product and desired video style.

        Returns:
            A :class:`~orchestrator.schemas.media.MediaAsset` representing the
            generated video.
        """
        ...


class MediaGeneratorProtocol(ImageGeneratorProtocol, VideoGeneratorProtocol, Protocol):
    """Combined protocol for services that generate both images and videos.

    Satisfies the Interface Segregation Principle (ISP) by composing the two
    focused sub-protocols into a single, broader contract.
    """
