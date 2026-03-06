"""Tests for the prompt engine service."""

from orchestrator.schemas.media import (
    CameraAngle,
    ImageGenerationRequest,
    ImageStyle,
    VideoGenerationRequest,
    VideoStyle,
)
from orchestrator.services.prompt_engine import (
    _ML_COMPLIANCE_DIRECTIVES,
    PromptEngine,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_ENGINE = PromptEngine()

_IMAGE_REQUEST = ImageGenerationRequest(
    product_sku="CASE-001",
    case_name="NZXT H510",
    component_summary="AMD Ryzen 5 5600X, 16 GB DDR4, RTX 3080",
    tier="Gaming",
)

_VIDEO_REQUEST = VideoGenerationRequest(
    product_sku="CASE-001",
    case_name="NZXT H510",
    component_summary="AMD Ryzen 5 5600X, 16 GB DDR4, RTX 3080",
    tier="Gaming",
    style=VideoStyle.TECH_SHOWCASE,
    camera_angle=CameraAngle.DOLLY_ZOOM,
    include_spec_overlays=True,
    spec_overlay_texts=["16 GB VRAM", "PCIe 4.0"],
)


# ---------------------------------------------------------------------------
# Image prompt — compliance directives (FR-3.5)
# ---------------------------------------------------------------------------


class TestImagePromptCompliance:
    """Image prompts must include MercadoLibre Rule 25505 directives."""

    def test_image_prompt_contains_compliance_directives(self) -> None:
        """ML compliance directives must appear in every image prompt."""
        prompt = _ENGINE.build_image_prompt(_IMAGE_REQUEST, ImageStyle.FRONT_VIEW)
        assert _ML_COMPLIANCE_DIRECTIVES in prompt


# ---------------------------------------------------------------------------
# Image prompt — style variations (FR-3.3)
# ---------------------------------------------------------------------------


class TestImagePromptStyles:
    """Image prompts vary by ImageStyle (4 distinct compositions)."""

    def test_image_prompt_front_view_style(self) -> None:
        """Front-view style produces a straight-on composition instruction."""
        prompt = _ENGINE.build_image_prompt(_IMAGE_REQUEST, ImageStyle.FRONT_VIEW)
        assert "front" in prompt.lower()
        assert "centred" in prompt.lower() or "centered" in prompt.lower()

    def test_image_prompt_three_quarter_style(self) -> None:
        """Three-quarter style produces an angled composition instruction."""
        prompt = _ENGINE.build_image_prompt(_IMAGE_REQUEST, ImageStyle.THREE_QUARTER)
        assert "three-quarter" in prompt.lower() or "45" in prompt

    def test_image_prompt_detail_closeup_style(self) -> None:
        """Detail-closeup style focuses on product details."""
        prompt = _ENGINE.build_image_prompt(_IMAGE_REQUEST, ImageStyle.DETAIL_CLOSEUP)
        assert "close-up" in prompt.lower() or "closeup" in prompt.lower()

    def test_image_prompt_lifestyle_context_style(self) -> None:
        """Lifestyle-context style places product in a room/desk setting."""
        prompt = _ENGINE.build_image_prompt(_IMAGE_REQUEST, ImageStyle.LIFESTYLE_CONTEXT)
        assert "desk" in prompt.lower() or "room" in prompt.lower()

    def test_all_styles_produce_distinct_prompts(self) -> None:
        """Each style must yield a different prompt string."""
        prompts = {style: _ENGINE.build_image_prompt(_IMAGE_REQUEST, style) for style in ImageStyle}
        assert len(set(prompts.values())) == len(ImageStyle)


# ---------------------------------------------------------------------------
# Image prompt — build data context
# ---------------------------------------------------------------------------


class TestImagePromptContext:
    """Image prompts include case name, component summary, and tier context."""

    def test_image_prompt_includes_case_name(self) -> None:
        """The case model name must appear in the image prompt."""
        prompt = _ENGINE.build_image_prompt(_IMAGE_REQUEST, ImageStyle.FRONT_VIEW)
        assert "NZXT H510" in prompt

    def test_image_prompt_includes_component_summary(self) -> None:
        """The component summary must appear in the image prompt."""
        prompt = _ENGINE.build_image_prompt(_IMAGE_REQUEST, ImageStyle.FRONT_VIEW)
        assert "AMD Ryzen 5 5600X" in prompt
        assert "RTX 3080" in prompt

    def test_image_prompt_tier_context(self) -> None:
        """Tier-specific context appears in the image prompt."""
        for tier, keyword in [
            ("Home", "home"),
            ("Business", "professional"),
            ("Gaming", "gaming"),
        ]:
            request = ImageGenerationRequest(
                product_sku="CASE-001",
                case_name="Generic Case",
                tier=tier,
            )
            prompt = _ENGINE.build_image_prompt(request, ImageStyle.LIFESTYLE_CONTEXT)
            assert keyword in prompt.lower(), (
                f"Tier '{tier}' should produce a prompt containing '{keyword}'"
            )


# ---------------------------------------------------------------------------
# Video prompt — compliance (FR-3.5)
# ---------------------------------------------------------------------------


class TestVideoPromptCompliance:
    """Video prompts must include MercadoLibre Rule 25505 directives."""

    def test_video_prompt_contains_compliance_directives(self) -> None:
        """ML compliance directives must appear in every video prompt."""
        prompt = _ENGINE.build_video_prompt(_VIDEO_REQUEST)
        assert _ML_COMPLIANCE_DIRECTIVES in prompt


# ---------------------------------------------------------------------------
# Video prompt — spec overlays (FR-3.4)
# ---------------------------------------------------------------------------


class TestVideoPromptSpecOverlays:
    """Video prompts include specification overlay instructions."""

    def test_video_prompt_includes_spec_overlays(self) -> None:
        """Spec overlay texts appear in the video prompt when enabled."""
        prompt = _ENGINE.build_video_prompt(_VIDEO_REQUEST)
        assert "16 GB VRAM" in prompt
        assert "PCIe 4.0" in prompt

    def test_video_prompt_no_overlays_when_disabled(self) -> None:
        """Spec overlays are omitted when include_spec_overlays is False."""
        request = VideoGenerationRequest(
            product_sku="CASE-001",
            case_name="NZXT H510",
            include_spec_overlays=False,
            spec_overlay_texts=["16 GB VRAM"],
        )
        prompt = _ENGINE.build_video_prompt(request)
        assert "16 GB VRAM" not in prompt


# ---------------------------------------------------------------------------
# Video prompt — style and angle (FR-3.3)
# ---------------------------------------------------------------------------


class TestVideoPromptStyleAndAngle:
    """Video prompts include style and camera angle instructions."""

    def test_video_prompt_includes_style_and_angle(self) -> None:
        """Style and camera angle values appear in the video prompt."""
        prompt = _ENGINE.build_video_prompt(_VIDEO_REQUEST)
        assert "tech_showcase" in prompt.lower() or "tech showcase" in prompt.lower()
        assert "dolly_zoom" in prompt.lower() or "dolly zoom" in prompt.lower()


# ---------------------------------------------------------------------------
# select_video_variation — determinism
# ---------------------------------------------------------------------------


class TestSelectVideoVariation:
    """select_video_variation is deterministic and varies by hash."""

    def test_select_video_variation_deterministic(self) -> None:
        """Same hash always produces the same style and angle."""
        tower_hash = "a" * 64
        first = _ENGINE.select_video_variation(tower_hash)
        second = _ENGINE.select_video_variation(tower_hash)
        assert first == second

    def test_select_video_variation_different_hashes(self) -> None:
        """Different hashes produce at least one different variation."""
        results = {_ENGINE.select_video_variation(c * 64) for c in "abcdef0123456789"}
        # With 16 distinct hashes we expect more than 1 unique (style, angle) pair.
        assert len(results) > 1

    def test_select_video_variation_returns_valid_enums(self) -> None:
        """Returned values are valid VideoStyle and CameraAngle members."""
        style, angle = _ENGINE.select_video_variation("f" * 64)
        assert isinstance(style, VideoStyle)
        assert isinstance(angle, CameraAngle)
