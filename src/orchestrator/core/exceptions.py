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
