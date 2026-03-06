"""Pydantic schemas for creative asset data structures."""

import enum

from pydantic import BaseModel, Field


class MediaType(enum.StrEnum):
    """Supported media asset types.

    Attributes:
        IMAGE: Static image asset.
        VIDEO: Video asset.
    """

    IMAGE = "image"
    VIDEO = "video"


class ImageStyle(enum.StrEnum):
    """Visual style variations for generated product images.

    Attributes:
        FRONT_VIEW: Direct front-facing product shot.
        THREE_QUARTER: Three-quarter angle perspective.
        DETAIL_CLOSEUP: Close-up detail shot of the product.
        LIFESTYLE_CONTEXT: Product shown in a lifestyle/usage context.
    """

    FRONT_VIEW = "front_view"
    THREE_QUARTER = "three_quarter"
    DETAIL_CLOSEUP = "detail_closeup"
    LIFESTYLE_CONTEXT = "lifestyle_context"


class VideoStyle(enum.StrEnum):
    """Visual style variations for generated product videos.

    Attributes:
        DRAMATIC_LIGHTING: High-contrast dramatic lighting setup.
        SOFT_STUDIO: Soft, diffused studio lighting.
        TECH_SHOWCASE: Technology-focused showcase presentation.
        MINIMALIST: Clean, minimal background and styling.
    """

    DRAMATIC_LIGHTING = "dramatic_lighting"
    SOFT_STUDIO = "soft_studio"
    TECH_SHOWCASE = "tech_showcase"
    MINIMALIST = "minimalist"


class CameraAngle(enum.StrEnum):
    """Camera movement/angle options for video generation.

    Attributes:
        ORBIT: Orbital rotation around the product.
        DOLLY_ZOOM: Dolly zoom (Hitchcock zoom) effect.
        LOW_ANGLE: Low-angle upward perspective.
        TOP_DOWN: Bird's-eye top-down view.
    """

    ORBIT = "orbit"
    DOLLY_ZOOM = "dolly_zoom"
    LOW_ANGLE = "low_angle"
    TOP_DOWN = "top_down"


class MediaAsset(BaseModel):
    """A generated creative media asset (image or video).

    Attributes:
        asset_id: Unique identifier for this asset.
        media_type: Whether this asset is an image or video.
        url: URL pointing to the generated asset.
        style: Style applied during generation; must be an ``ImageStyle`` or
            ``VideoStyle`` value.
        duration: Duration in seconds; only applicable for video assets.
    """

    asset_id: str
    media_type: MediaType
    url: str
    style: ImageStyle | VideoStyle
    duration: float | None = None


class ImageGenerationRequest(BaseModel):
    """Request schema for generating product images.

    Attributes:
        product_sku: SKU of the product to generate images for.
        styles: List of image styles to generate. Defaults to all four styles.
    """

    product_sku: str
    styles: list[ImageStyle] = Field(default_factory=lambda: list(ImageStyle))


class VideoGenerationRequest(BaseModel):
    """Request schema for generating a product video.

    Attributes:
        product_sku: SKU of the product to generate a video for.
        style: Visual style for the video. Defaults to ``VideoStyle.SOFT_STUDIO``.
        camera_angle: Camera movement/angle. Defaults to ``CameraAngle.ORBIT``.
        include_spec_overlays: Whether to overlay product specs on the video.
        spec_overlay_texts: List of specification text strings to display as overlays.
    """

    product_sku: str
    style: VideoStyle = VideoStyle.SOFT_STUDIO
    camera_angle: CameraAngle = CameraAngle.ORBIT
    include_spec_overlays: bool = False
    spec_overlay_texts: list[str] = Field(default_factory=list)


class ComplianceCheckResult(BaseModel):
    """Result of a compliance check on a generated creative asset.

    Attributes:
        is_compliant: Whether the asset passed all compliance checks.
        violations: List of violation descriptions if any were found.
    """

    is_compliant: bool = True
    violations: list[str] = Field(default_factory=list)


class CreativeResult(BaseModel):
    """Aggregated creative output for a product, combining images, video, and compliance.

    Attributes:
        product_sku: SKU of the product these assets belong to.
        images: List of generated image assets.
        video: Optional generated video asset.
        compliance: Optional compliance check result for the generated assets.
    """

    product_sku: str
    images: list[MediaAsset] = Field(default_factory=list)
    video: MediaAsset | None = None
    compliance: ComplianceCheckResult | None = None
