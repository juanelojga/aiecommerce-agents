"""Tests for the ML Rule 25505 media compliance validator."""

from orchestrator.schemas.media import (
    ImageStyle,
    MediaAsset,
    MediaType,
    VideoStyle,
)
from orchestrator.services.media_compliance import MediaComplianceValidator

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_VALIDATOR = MediaComplianceValidator()

_COMPLIANT_PROMPT = (
    "Generate a product photograph. "
    "MANDATORY RULES: Use a clean, neutral white or light grey background. "
    "No watermarks. No logos. No contact information. "
    "No promotional text overlays. No prices. Professional product photography style."
)

_NON_COMPLIANT_PROMPT = "Generate a product photograph with bright colors."


def _compliant_image(**overrides: object) -> MediaAsset:
    """Build a fully compliant image MediaAsset, with optional field overrides."""
    defaults: dict[str, object] = {
        "asset_id": "img-001",
        "media_type": MediaType.IMAGE,
        "url": "https://cdn.example.com/img-001.png",
        "style": ImageStyle.FRONT_VIEW,
        "width": 1024,
        "height": 1024,
        "mime_type": "image/png",
        "prompt": _COMPLIANT_PROMPT,
    }
    defaults.update(overrides)
    return MediaAsset(**defaults)


def _compliant_video(**overrides: object) -> MediaAsset:
    """Build a fully compliant video MediaAsset, with optional field overrides."""
    defaults: dict[str, object] = {
        "asset_id": "vid-001",
        "media_type": MediaType.VIDEO,
        "url": "https://cdn.example.com/vid-001.mp4",
        "style": VideoStyle.SOFT_STUDIO,
        "duration": 15.0,
        "width": 1920,
        "height": 1080,
        "mime_type": "video/mp4",
        "prompt": _COMPLIANT_PROMPT,
    }
    defaults.update(overrides)
    return MediaAsset(**defaults)


# ---------------------------------------------------------------------------
# Image validation
# ---------------------------------------------------------------------------


class TestValidateImageCompliant:
    """A fully compliant image asset must pass validation."""

    def test_validate_image_compliant(self) -> None:
        """Valid image passes all compliance checks."""
        result = _VALIDATOR.validate_image(_compliant_image())

        assert result.is_compliant is True
        assert result.violations == []


class TestValidateImageMissingUrl:
    """An image with a missing URL must fail validation."""

    def test_validate_image_missing_url(self) -> None:
        """Missing URL produces a violation."""
        asset = _compliant_image(url="")
        result = _VALIDATOR.validate_image(asset)

        assert result.is_compliant is False
        assert any("URL" in v for v in result.violations)


class TestValidateImageWrongMediaType:
    """An image asset with wrong media_type must fail validation."""

    def test_validate_image_wrong_media_type(self) -> None:
        """Wrong media_type produces a violation."""
        asset = _compliant_image(media_type=MediaType.VIDEO)
        result = _VALIDATOR.validate_image(asset)

        assert result.is_compliant is False
        assert any("media_type" in v for v in result.violations)


class TestValidateImageInvalidDimensions:
    """An image with dimensions outside allowed range must fail validation."""

    def test_validate_image_dimensions_too_small(self) -> None:
        """Dimensions below the minimum produce a violation."""
        asset = _compliant_image(width=200, height=200)
        result = _VALIDATOR.validate_image(asset)

        assert result.is_compliant is False
        assert any("dimensions" in v.lower() for v in result.violations)

    def test_validate_image_dimensions_too_large(self) -> None:
        """Dimensions above the maximum produce a violation."""
        asset = _compliant_image(width=4096, height=4096)
        result = _VALIDATOR.validate_image(asset)

        assert result.is_compliant is False
        assert any("dimensions" in v.lower() for v in result.violations)


class TestValidateImagePromptMissingCompliance:
    """An image whose prompt lacks compliance directives must fail validation."""

    def test_validate_image_prompt_missing_compliance(self) -> None:
        """Missing compliance directives in the prompt produce a violation."""
        asset = _compliant_image(prompt=_NON_COMPLIANT_PROMPT)
        result = _VALIDATOR.validate_image(asset)

        assert result.is_compliant is False
        assert any("compliance" in v.lower() or "directive" in v.lower() for v in result.violations)


# ---------------------------------------------------------------------------
# Video validation
# ---------------------------------------------------------------------------


class TestValidateVideoCompliant:
    """A fully compliant video asset must pass validation."""

    def test_validate_video_compliant(self) -> None:
        """Valid video passes all compliance checks."""
        result = _VALIDATOR.validate_video(_compliant_video())

        assert result.is_compliant is True
        assert result.violations == []


class TestValidateVideoMissingDuration:
    """A video with missing duration must fail validation."""

    def test_validate_video_missing_duration(self) -> None:
        """Missing duration produces a violation."""
        asset = _compliant_video(duration=None)
        result = _VALIDATOR.validate_video(asset)

        assert result.is_compliant is False
        assert any("duration" in v.lower() for v in result.violations)


class TestValidateVideoWrongMediaType:
    """A video asset with wrong media_type must fail validation."""

    def test_validate_video_wrong_media_type(self) -> None:
        """Wrong media_type produces a violation."""
        asset = _compliant_video(media_type=MediaType.IMAGE)
        result = _VALIDATOR.validate_video(asset)

        assert result.is_compliant is False
        assert any("media_type" in v for v in result.violations)


class TestValidateVideoPromptMissingCompliance:
    """A video whose prompt lacks compliance directives must fail validation."""

    def test_validate_video_prompt_missing_compliance(self) -> None:
        """Missing compliance directives in the prompt produce a violation."""
        asset = _compliant_video(prompt=_NON_COMPLIANT_PROMPT)
        result = _VALIDATOR.validate_video(asset)

        assert result.is_compliant is False
        assert any("compliance" in v.lower() or "directive" in v.lower() for v in result.violations)


# ---------------------------------------------------------------------------
# Aggregate validation
# ---------------------------------------------------------------------------


class TestValidateAllCompliant:
    """All compliant assets must pass aggregate validation."""

    def test_validate_all_all_compliant(self) -> None:
        """All valid assets → compliant."""
        images = [_compliant_image(asset_id=f"img-{i:03d}") for i in range(4)]
        video = _compliant_video()
        result = _VALIDATOR.validate_all(images, video)

        assert result.is_compliant is True
        assert result.violations == []


class TestValidateAllOneViolation:
    """A single bad asset causes the entire batch to fail."""

    def test_validate_all_one_violation(self) -> None:
        """One non-compliant asset → non-compliant batch."""
        images = [
            _compliant_image(asset_id="img-001"),
            _compliant_image(asset_id="img-002", url=""),  # bad URL
        ]
        video = _compliant_video()
        result = _VALIDATOR.validate_all(images, video)

        assert result.is_compliant is False
        assert len(result.violations) >= 1


class TestValidateAllNoVideo:
    """Images-only validation works when video is ``None``."""

    def test_validate_all_no_video(self) -> None:
        """Images-only validation succeeds when all images are compliant."""
        images = [_compliant_image(asset_id=f"img-{i:03d}") for i in range(2)]
        result = _VALIDATOR.validate_all(images, None)

        assert result.is_compliant is True
        assert result.violations == []
