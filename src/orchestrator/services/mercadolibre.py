"""MercadoLibre API client.

Wraps all outbound HTTP calls to the MercadoLibre platform behind
an async interface with OAuth2 token management, retry logic,
and exponential backoff.
"""

import asyncio
import logging

import httpx

from orchestrator.core.config import Settings
from orchestrator.core.exceptions import MercadoLibreError
from orchestrator.schemas.mercadolibre import (
    MLListingRequest,
    MLListingResponse,
    MLMediaUploadResponse,
    MLTokenResponse,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 5.0  # seconds


class MercadoLibreClient:
    """Async HTTP client for the MercadoLibre API.

    Handles OAuth2 token management, listing CRUD, and media upload
    with retry logic and exponential backoff.

    Args:
        settings: Application settings containing ML API credentials.
    """

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.MERCADOLIBRE_API_URL
        self._access_token = settings.MERCADOLIBRE_ACCESS_TOKEN
        self._current_refresh_token = settings.MERCADOLIBRE_REFRESH_TOKEN
        self._client_id = settings.MERCADOLIBRE_CLIENT_ID
        self._client_secret = settings.MERCADOLIBRE_CLIENT_SECRET

    # ── Public API ──────────────────────────────────────────────────────

    async def create_listing(self, listing: MLListingRequest) -> MLListingResponse:
        """Create a new listing on MercadoLibre.

        Calls ``POST /items`` with the listing payload.

        Args:
            listing: Typed request payload describing the listing.

        Returns:
            Typed :class:`MLListingResponse` with the created listing details.

        Raises:
            MercadoLibreError: If the API call fails.
        """
        data = await self._request_with_retry(
            method="POST",
            path="/items",
            json_data=listing.model_dump(exclude_none=True),
        )
        return MLListingResponse.model_validate(data)

    async def update_listing(self, ml_id: str, updates: dict[str, object]) -> MLListingResponse:
        """Update an existing listing.

        Calls ``PUT /items/{ml_id}`` with the update payload.

        Args:
            ml_id: MercadoLibre listing identifier (e.g. ``"MLA123456789"``).
            updates: Dictionary of fields to update on the listing.

        Returns:
            Typed :class:`MLListingResponse` with the updated listing details.

        Raises:
            MercadoLibreError: If the API call fails.
        """
        data = await self._request_with_retry(
            method="PUT",
            path=f"/items/{ml_id}",
            json_data=updates,
        )
        return MLListingResponse.model_validate(data)

    async def pause_listing(self, ml_id: str) -> MLListingResponse:
        """Pause an active listing.

        Calls ``PUT /items/{ml_id}`` with ``{"status": "paused"}``.

        Args:
            ml_id: MercadoLibre listing identifier to pause.

        Returns:
            Typed :class:`MLListingResponse` with the paused listing details.

        Raises:
            MercadoLibreError: If the API call fails.
        """
        return await self.update_listing(ml_id, {"status": "paused"})

    async def upload_image(self, image_url: str) -> str:
        """Upload image, return ML picture ID.

        Calls ``POST /pictures/items/upload`` with the image source URL.

        Args:
            image_url: Public URL of the image to upload.

        Returns:
            MercadoLibre picture identifier for the uploaded image.

        Raises:
            MercadoLibreError: If the upload fails.
        """
        data = await self._request_with_retry(
            method="POST",
            path="/pictures/items/upload",
            json_data={"source": image_url},
        )
        response = MLMediaUploadResponse.model_validate(data)
        return response.id

    async def upload_video(self, video_url: str) -> str:
        """Upload video, return ML video ID.

        Calls ``POST /items/videos/upload`` with the video source URL.

        Args:
            video_url: Public URL of the video to upload.

        Returns:
            MercadoLibre video identifier for the uploaded video.

        Raises:
            MercadoLibreError: If the upload fails.
        """
        data = await self._request_with_retry(
            method="POST",
            path="/items/videos/upload",
            json_data={"source": video_url},
        )
        response = MLMediaUploadResponse.model_validate(data)
        return response.id

    # ── Internal helpers ────────────────────────────────────────────────

    async def _refresh_token(self) -> None:
        """Refresh OAuth2 access token using refresh token.

        Calls ``POST /oauth/token`` with the current refresh token and
        updates the stored access and refresh tokens on success.

        Raises:
            MercadoLibreError: If the token refresh request fails.
        """
        async with httpx.AsyncClient(base_url=self._base_url) as client:
            response = await client.post(
                "/oauth/token",
                json={
                    "grant_type": "refresh_token",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._current_refresh_token,
                },
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise MercadoLibreError(
                    message="Token refresh failed",
                    status_code=exc.response.status_code,
                ) from exc

            token_data = MLTokenResponse.model_validate(response.json())
            self._access_token = token_data.access_token
            self._current_refresh_token = token_data.refresh_token

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        json_data: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Authenticated request with retry and auto token refresh on 401.

        Client errors (4xx, excluding 401) are raised immediately without
        retrying. Server errors (5xx) and network errors are retried up to
        ``_MAX_RETRIES`` times with exponential backoff starting at
        ``_BACKOFF_BASE`` seconds. On a 401 response, the token is refreshed
        once and the request is retried.

        Args:
            method: HTTP method (e.g. ``"GET"``, ``"POST"``, ``"PUT"``).
            path: API path relative to the base URL.
            json_data: Optional JSON body for the request.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            MercadoLibreError: If the request fails after all retries or
                immediately on a non-401 client error.
        """
        last_exc: Exception | None = None
        token_refreshed = False

        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    base_url=self._base_url,
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "Content-Type": "application/json",
                    },
                ) as client:
                    response = await client.request(method, path, json=json_data)
                    response.raise_for_status()
                    return response.json()  # type: ignore[no-any-return]
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code

                # Auto-refresh token on 401 (only once)
                if status == 401 and not token_refreshed:
                    token_refreshed = True
                    await self._refresh_token()
                    continue

                # Do not retry other client errors (4xx)
                if status < 500:
                    try:
                        error_body = exc.response.json()
                    except Exception:
                        error_body = {}
                    raise MercadoLibreError(
                        message=str(error_body.get("message", str(exc))),
                        status_code=status,
                        ml_error_code=str(error_body.get("error", "")),
                    ) from exc
            except httpx.RequestError as exc:
                last_exc = exc

            if attempt < _MAX_RETRIES:
                delay = _BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "ML request %s %s failed (attempt %d/%d), retrying in %.0fs",
                    method,
                    path,
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)

        raise MercadoLibreError(str(last_exc)) from last_exc
