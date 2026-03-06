"""Post-generation compliance validator for MercadoLibre Rule 25505.

Validates generated creative assets against MercadoLibre marketplace
requirements including URL validity, MIME types, dimensions, duration,
and prompt-level compliance directives.

This module is pure logic with no external dependencies, making it
trivially testable and fully deterministic.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

from orchestrator.schemas.media import ComplianceCheckResult, MediaAsset, MediaType

# ---------------------------------------------------------------------------
# ML Rule 25505 — Accepted formats and dimension constraints
# ---------------------------------------------------------------------------

_ALLOWED_IMAGE_MIME_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"})
_ALLOWED_VIDEO_MIME_TYPES: frozenset[str] = frozenset({"video/mp4"})

_IMAGE_MIN_WIDTH: int = 500
_IMAGE_MIN_HEIGHT: int = 500
_IMAGE_MAX_WIDTH: int = 2048
_IMAGE_MAX_HEIGHT: int = 2048

_VIDEO_MIN_WIDTH: int = 640
_VIDEO_MIN_HEIGHT: int = 480

_VIDEO_MIN_DURATION: float = 5.0
_VIDEO_MAX_DURATION: float = 60.0

# Compliance keywords that *must* appear in every generation prompt.
_REQUIRED_PROMPT_KEYWORDS: tuple[str, ...] = (
    "no watermarks",
    "no logos",
    "no contact information",
    "no promotional text overlays",
)

_URL_PATTERN: re.Pattern[str] = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


class MediaComplianceValidator:
    """Validates generated media assets against MercadoLibre Rule 25505.

    All methods are pure functions with no side effects, ensuring
    identical inputs always produce identical outputs.
    """

    # ------------------------------------------------------------------
    # Image validation
    # ------------------------------------------------------------------

    def validate_image(self, asset: MediaAsset) -> ComplianceCheckResult:
        """Validate a single image asset for ML Rule 25505 compliance.

        Checks URL format, media type, MIME type, dimensions, and
        whether the generation prompt contains required compliance
        directives.

        Args:
            asset: The image ``MediaAsset`` to validate.

        Returns:
            A ``ComplianceCheckResult`` indicating compliance status and
            any violation descriptions.
        """
        violations: list[str] = []

        self._check_url(asset, violations)
        self._check_media_type(asset, MediaType.IMAGE, violations)
        self._check_mime_type(asset, _ALLOWED_IMAGE_MIME_TYPES, violations)
        self._check_image_dimensions(asset, violations)
        self._check_prompt_compliance(asset, violations)

        return ComplianceCheckResult(
            is_compliant=len(violations) == 0,
            violations=violations,
        )

    # ------------------------------------------------------------------
    # Video validation
    # ------------------------------------------------------------------

    def validate_video(self, asset: MediaAsset) -> ComplianceCheckResult:
        """Validate a single video asset for ML Rule 25505 compliance.

        Checks URL format, media type, MIME type, dimensions, duration
        range, and whether the generation prompt contains required
        compliance directives.

        Args:
            asset: The video ``MediaAsset`` to validate.

        Returns:
            A ``ComplianceCheckResult`` indicating compliance status and
            any violation descriptions.
        """
        violations: list[str] = []

        self._check_url(asset, violations)
        self._check_media_type(asset, MediaType.VIDEO, violations)
        self._check_mime_type(asset, _ALLOWED_VIDEO_MIME_TYPES, violations)
        self._check_video_dimensions(asset, violations)
        self._check_video_duration(asset, violations)
        self._check_prompt_compliance(asset, violations)

        return ComplianceCheckResult(
            is_compliant=len(violations) == 0,
            violations=violations,
        )

    # ------------------------------------------------------------------
    # Aggregate validation
    # ------------------------------------------------------------------

    def validate_all(
        self,
        images: Sequence[MediaAsset],
        video: MediaAsset | None,
    ) -> ComplianceCheckResult:
        """Validate all assets; any single violation fails the whole check.

        Args:
            images: List of image ``MediaAsset`` instances to validate.
            video: Optional video ``MediaAsset`` to validate.

        Returns:
            An aggregated ``ComplianceCheckResult``. ``is_compliant`` is
            ``True`` only when every asset passes individually.
        """
        all_violations: list[str] = []

        for img in images:
            result = self.validate_image(img)
            all_violations.extend(result.violations)

        if video is not None:
            result = self.validate_video(video)
            all_violations.extend(result.violations)

        return ComplianceCheckResult(
            is_compliant=len(all_violations) == 0,
            violations=all_violations,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_url(asset: MediaAsset, violations: list[str]) -> None:
        """Verify the asset URL is present and well-formed."""
        if not asset.url:
            violations.append(f"Asset '{asset.asset_id}': URL is missing.")
        elif not _URL_PATTERN.match(asset.url):
            violations.append(
                f"Asset '{asset.asset_id}': URL '{asset.url}' is not a valid HTTP(S) URL."
            )

    @staticmethod
    def _check_media_type(
        asset: MediaAsset,
        expected: MediaType,
        violations: list[str],
    ) -> None:
        """Verify the asset has the expected media type."""
        if asset.media_type != expected:
            violations.append(
                f"Asset '{asset.asset_id}': Expected media_type '{expected.value}' "
                f"but got '{asset.media_type.value}'."
            )

    @staticmethod
    def _check_mime_type(
        asset: MediaAsset,
        allowed: frozenset[str],
        violations: list[str],
    ) -> None:
        """Verify the MIME type is in the allowed set (if provided)."""
        if asset.mime_type is not None and asset.mime_type not in allowed:
            violations.append(
                f"Asset '{asset.asset_id}': MIME type '{asset.mime_type}' is not allowed. "
                f"Accepted: {', '.join(sorted(allowed))}."
            )

    @staticmethod
    def _check_image_dimensions(asset: MediaAsset, violations: list[str]) -> None:
        """Verify image width/height fall within ML Rule 25505 bounds."""
        if asset.width is not None and asset.height is not None:
            if asset.width < _IMAGE_MIN_WIDTH or asset.height < _IMAGE_MIN_HEIGHT:
                violations.append(
                    f"Asset '{asset.asset_id}': Image dimensions {asset.width}x{asset.height} "
                    f"are below the minimum {_IMAGE_MIN_WIDTH}x{_IMAGE_MIN_HEIGHT}."
                )
            if asset.width > _IMAGE_MAX_WIDTH or asset.height > _IMAGE_MAX_HEIGHT:
                violations.append(
                    f"Asset '{asset.asset_id}': Image dimensions {asset.width}x{asset.height} "
                    f"exceed the maximum {_IMAGE_MAX_WIDTH}x{_IMAGE_MAX_HEIGHT}."
                )

    @staticmethod
    def _check_video_dimensions(asset: MediaAsset, violations: list[str]) -> None:
        """Verify video width/height meet ML Rule 25505 minimum."""
        if (
            asset.width is not None
            and asset.height is not None
            and (asset.width < _VIDEO_MIN_WIDTH or asset.height < _VIDEO_MIN_HEIGHT)
        ):
            violations.append(
                f"Asset '{asset.asset_id}': Video dimensions {asset.width}x{asset.height} "
                f"are below the minimum {_VIDEO_MIN_WIDTH}x{_VIDEO_MIN_HEIGHT}."
            )

    @staticmethod
    def _check_video_duration(asset: MediaAsset, violations: list[str]) -> None:
        """Verify video duration is present and within allowed range."""
        if asset.duration is None:
            violations.append(f"Asset '{asset.asset_id}': Video duration is missing.")
        elif asset.duration < _VIDEO_MIN_DURATION or asset.duration > _VIDEO_MAX_DURATION:
            violations.append(
                f"Asset '{asset.asset_id}': Video duration {asset.duration}s is outside "
                f"the allowed range ({_VIDEO_MIN_DURATION}-{_VIDEO_MAX_DURATION}s)."
            )

    @staticmethod
    def _check_prompt_compliance(asset: MediaAsset, violations: list[str]) -> None:
        """Verify the generation prompt contains required compliance directives."""
        if asset.prompt is None:
            return

        prompt_lower = asset.prompt.lower()
        missing = [kw for kw in _REQUIRED_PROMPT_KEYWORDS if kw not in prompt_lower]
        if missing:
            violations.append(
                f"Asset '{asset.asset_id}': Prompt is missing required compliance "
                f"directives: {', '.join(missing)}."
            )
