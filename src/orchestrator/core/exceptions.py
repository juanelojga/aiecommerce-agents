"""Custom exception hierarchy for the orchestrator application.

All application-specific exceptions inherit from ``OrchestratorError`` so
callers can catch the base class when a broad handler is sufficient, or catch
a specific subclass when finer-grained handling is needed.
"""

from http import HTTPStatus


class OrchestratorError(Exception):
    """Base exception for all orchestrator errors.

    Attributes:
        message: Human-readable description of the error.
        STATUS_CODE: HTTP status code that should be returned to the client.
    """

    STATUS_CODE: int = HTTPStatus.INTERNAL_SERVER_ERROR.value

    def __init__(self, message: str) -> None:
        """Initialise with a descriptive message.

        Args:
            message: Human-readable description of what went wrong.
        """
        super().__init__(message)
        self.message = message


class APIClientError(OrchestratorError):
    """Error communicating with an external API.

    Raised when an outbound HTTP request to a third-party service fails or
    returns an unexpected response.
    """

    STATUS_CODE: int = HTTPStatus.BAD_GATEWAY.value


class InventoryError(OrchestratorError):
    """Error fetching or processing inventory data.

    Raised when inventory data cannot be retrieved or is in an invalid state.
    """

    STATUS_CODE: int = HTTPStatus.SERVICE_UNAVAILABLE.value


class CompatibilityError(OrchestratorError):
    """Components failed compatibility validation.

    Raised when a set of selected components does not meet the compatibility
    rules required to form a valid tower build.
    """

    STATUS_CODE: int = HTTPStatus.UNPROCESSABLE_ENTITY.value


class UniquenessError(OrchestratorError):
    """Could not generate a unique build combination.

    Raised when the build generator exhausts all possible permutations without
    producing a combination that has not been seen before.
    """

    STATUS_CODE: int = HTTPStatus.CONFLICT.value


class TowerNotFoundError(OrchestratorError):
    """Requested tower does not exist in the registry.

    Raised when a lookup by identifier (e.g. hash) returns no result.
    """

    STATUS_CODE: int = HTTPStatus.NOT_FOUND.value


class BundleNotFoundError(OrchestratorError):
    """Requested bundle does not exist in the registry.

    Raised when a bundle lookup by identifier returns no result.
    """

    STATUS_CODE: int = HTTPStatus.NOT_FOUND.value


class MediaGenerationError(OrchestratorError):
    """Error generating media content via an AI provider.

    Raised when a media generation request (e.g. image, video) fails or
    returns an invalid result from the underlying provider.

    Attributes:
        media_type: The type of media being generated (e.g. ``"image"``).
        provider: The AI provider that was used (e.g. ``"gemini"``).
    """

    STATUS_CODE: int = HTTPStatus.INTERNAL_SERVER_ERROR.value

    def __init__(self, message: str, media_type: str = "", provider: str = "") -> None:
        """Initialise with a descriptive message and optional context.

        Args:
            message: Human-readable description of what went wrong.
            media_type: Type of media being generated (e.g. ``"image"``).
            provider: AI provider that raised the error (e.g. ``"gemini"``).
        """
        super().__init__(message)
        self.media_type = media_type
        self.provider = provider


class MediaComplianceError(OrchestratorError):
    """Generated media failed compliance or content-policy validation.

    Raised when the compliance validator detects policy violations in
    AI-generated media content.

    Attributes:
        violations: List of policy violation descriptions detected.
    """

    STATUS_CODE: int = HTTPStatus.UNPROCESSABLE_ENTITY.value

    def __init__(self, message: str, violations: list[str] | None = None) -> None:
        """Initialise with a descriptive message and optional violation list.

        Args:
            message: Human-readable description of what went wrong.
            violations: Policy violations detected; defaults to an empty list.
        """
        super().__init__(message)
        self.violations: list[str] = violations if violations is not None else []
