"""Security utilities and authentication helpers."""

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from orchestrator.core.config import Settings, get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


async def verify_api_key(
    api_key: str = Depends(api_key_header),
    settings: Settings = Depends(get_settings),
) -> str:
    """Validate the API key from the X-API-Key request header.

    Args:
        api_key: The API key extracted from the request header.
        settings: Application settings containing the expected API key.

    Returns:
        The validated API key string.

    Raises:
        HTTPException: 401 if the key is missing or does not match the configured key.
    """
    if not settings.API_KEY or api_key != settings.API_KEY:
        # ``not settings.API_KEY`` ensures all requests are rejected when the
        # key is unconfigured (empty default), providing a secure-by-default
        # posture rather than accidentally allowing open access.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key
