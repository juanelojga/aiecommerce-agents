"""Deterministic prompt engine for Gemini media generation.

Constructs image and video prompts from build data, ensuring
MercadoLibre Rule 25505 compliance (FR-3.5) in every prompt,
parameterized visual style variation (FR-3.3), and spec overlay
instructions for videos (FR-3.4).

This module is pure logic with no external dependencies, making it
trivially testable and fully deterministic.
"""

from orchestrator.schemas.media import (
    CameraAngle,
    ImageGenerationRequest,
    ImageStyle,
    VideoGenerationRequest,
    VideoStyle,
)

# ---------------------------------------------------------------------------
# MercadoLibre Rule 25505 compliance block (FR-3.5)
# ---------------------------------------------------------------------------

_ML_COMPLIANCE_DIRECTIVES: str = (
    "MANDATORY RULES: Use a clean, neutral white or light grey background. "
    "No watermarks. No logos. No contact information. "
    "No promotional text overlays. No prices. Professional product photography style."
)

# ---------------------------------------------------------------------------
# Per-style composition directives for images (FR-3.3)
# ---------------------------------------------------------------------------

_IMAGE_STYLE_DIRECTIVES: dict[ImageStyle, str] = {
    ImageStyle.FRONT_VIEW: (
        "Shoot the product straight-on from the front, centred in frame, "
        "with even, diffused lighting for a clean product hero shot."
    ),
    ImageStyle.THREE_QUARTER: (
        "Position the product at a three-quarter angle (roughly 45 degrees) "
        "to reveal depth and side detail with subtle shadow."
    ),
    ImageStyle.DETAIL_CLOSEUP: (
        "Capture an extreme close-up of a key product detail — ports, vents, "
        "texture — with shallow depth of field."
    ),
    ImageStyle.LIFESTYLE_CONTEXT: (
        "Place the product on a modern desk or in a room setting that matches "
        "its tier, showing it in use with peripherals."
    ),
}

# ---------------------------------------------------------------------------
# Tier-specific contextual descriptions
# ---------------------------------------------------------------------------

_TIER_CONTEXT: dict[str, str] = {
    "Home": "a casual home-office environment with warm, inviting tones",
    "Business": "a professional corporate workspace with clean, modern aesthetics",
    "Gaming": "a high-end gaming setup with RGB accents and dramatic flair",
}


class PromptEngine:
    """Constructs deterministic Gemini API prompts from build data.

    All methods are pure functions with no side effects, ensuring identical
    inputs always produce identical outputs.
    """

    def build_image_prompt(
        self,
        request: ImageGenerationRequest,
        style: ImageStyle,
    ) -> str:
        """Build a Gemini image-generation prompt.

        Assembles the prompt from the case name, component summary,
        style-specific composition directives, tier context, and
        MercadoLibre compliance rules.

        Args:
            request: Image generation request containing product context.
            style: Visual style determining the composition instructions.

        Returns:
            A fully-formed prompt string ready for the Gemini API.
        """
        parts: list[str] = []

        # Product identity
        subject = request.case_name or request.product_sku
        parts.append(f"Generate a product photograph of the {subject} PC tower.")

        # Component summary
        if request.component_summary:
            parts.append(f"Key components: {request.component_summary}.")

        # Style-specific composition
        parts.append(_IMAGE_STYLE_DIRECTIVES[style])

        # Tier-specific context
        if request.tier and request.tier in _TIER_CONTEXT:
            parts.append(f"Context: {_TIER_CONTEXT[request.tier]}.")

        # Compliance (always last so it's the final instruction)
        parts.append(_ML_COMPLIANCE_DIRECTIVES)

        return " ".join(parts)

    def build_video_prompt(self, request: VideoGenerationRequest) -> str:
        """Build a Gemini video-generation prompt.

        Assembles the prompt from the case name, visual style, camera
        angle, optional spec overlays (FR-3.4), and MercadoLibre
        compliance rules.

        Args:
            request: Video generation request containing product context
                and style/angle parameters.

        Returns:
            A fully-formed prompt string ready for the Gemini API.
        """
        parts: list[str] = []

        # Product identity
        subject = request.case_name or request.product_sku
        parts.append(f"Create a 5-second product showcase video of the {subject} PC tower.")

        # Style and camera angle (FR-3.3)
        parts.append(
            f"Visual style: {request.style.value}. Camera movement: {request.camera_angle.value}."
        )

        # Component summary
        if request.component_summary:
            parts.append(f"Key components: {request.component_summary}.")

        # Tier-specific context
        if request.tier and request.tier in _TIER_CONTEXT:
            parts.append(f"Context: {_TIER_CONTEXT[request.tier]}.")

        # Spec overlays (FR-3.4)
        if request.include_spec_overlays and request.spec_overlay_texts:
            overlay_str = "; ".join(request.spec_overlay_texts)
            parts.append(f"Overlay the following specifications as text on screen: {overlay_str}.")

        # Compliance (always last)
        parts.append(_ML_COMPLIANCE_DIRECTIVES)

        return " ".join(parts)

    def select_video_variation(
        self,
        tower_hash: str,
    ) -> tuple[VideoStyle, CameraAngle]:
        """Deterministically select a video style and camera angle from a hash.

        Uses the first 8 hex characters of the tower hash to derive
        indices into the ``VideoStyle`` and ``CameraAngle`` enums.
        The same hash always produces the same pair; different hashes
        are distributed across all valid combinations.

        Args:
            tower_hash: 64-character hex SHA-256 hash of the tower build.

        Returns:
            A ``(VideoStyle, CameraAngle)`` tuple.
        """
        hash_int = int(tower_hash[:8], 16)
        video_styles = list(VideoStyle)
        camera_angles = list(CameraAngle)

        style_idx = hash_int % len(video_styles)
        angle_idx = (hash_int // len(video_styles)) % len(camera_angles)

        return video_styles[style_idx], camera_angles[angle_idx]
