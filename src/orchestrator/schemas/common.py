"""Common Pydantic schemas shared across the application."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Schema for the health-check response.

    Attributes:
        status: A short string describing the service health.
    """

    status: str


class ErrorResponse(BaseModel):
    """Standard error response envelope.

    Attributes:
        detail: A human-readable error message.
    """

    detail: str
