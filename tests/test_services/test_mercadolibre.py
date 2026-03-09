"""Tests for MercadoLibreClient service."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from orchestrator.core.config import Settings
from orchestrator.core.exceptions import MercadoLibreError
from orchestrator.schemas.mercadolibre import MLListingRequest, MLListingResponse
from orchestrator.services.mercadolibre import (
    _BACKOFF_BASE,
    _MAX_RETRIES,
    MercadoLibreClient,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

VALID_LISTING_RESPONSE: dict[str, object] = {
    "id": "MLA123456789",
    "title": "RTX 4090 Gaming PC",
    "price": 2500.0,
    "status": "active",
    "permalink": "https://www.mercadolibre.com.ar/MLA123456789",
}

VALID_TOKEN_RESPONSE: dict[str, object] = {
    "access_token": "APP_USR-new-token",
    "token_type": "bearer",
    "expires_in": 21600,
    "refresh_token": "TG-new-refresh",
}

VALID_MEDIA_RESPONSE: dict[str, object] = {
    "id": "MEDIA-001",
    "status": "processed",
}


@pytest.fixture
def settings() -> Settings:
    """Return settings configured with dummy ML credentials."""
    return Settings(
        MERCADOLIBRE_API_URL="https://api.mercadolibre.com",
        MERCADOLIBRE_ACCESS_TOKEN="test-access-token",
        MERCADOLIBRE_REFRESH_TOKEN="test-refresh-token",
        MERCADOLIBRE_CLIENT_ID="test-client-id",
        MERCADOLIBRE_CLIENT_SECRET="test-client-secret",
    )


@pytest.fixture
def client(settings: Settings) -> MercadoLibreClient:
    """Return a MercadoLibreClient configured with dummy settings."""
    return MercadoLibreClient(settings)


@pytest.fixture
def listing_request() -> MLListingRequest:
    """Return a sample MLListingRequest."""
    return MLListingRequest(
        title="RTX 4090 Gaming PC",
        category_id="MLA1234",
        price=2500.0,
        description="High-end gaming tower.",
    )


def _make_response(status_code: int, json_data: object) -> MagicMock:
    """Build a mock httpx.Response with the given status and JSON payload."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    if status_code >= 400:
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=mock_resp,
        )
    else:
        mock_resp.raise_for_status.return_value = None
    return mock_resp


# ---------------------------------------------------------------------------
# create_listing
# ---------------------------------------------------------------------------


class TestCreateListing:
    """Tests for MercadoLibreClient.create_listing."""

    @pytest.mark.asyncio
    async def test_create_listing_success(
        self,
        client: MercadoLibreClient,
        listing_request: MLListingRequest,
    ) -> None:
        """Returns typed MLListingResponse on success."""
        mock_resp = _make_response(200, VALID_LISTING_RESPONSE)
        mock_request = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.request = mock_request
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.create_listing(listing_request)

        assert isinstance(result, MLListingResponse)
        assert result.id == "MLA123456789"
        assert result.title == "RTX 4090 Gaming PC"
        assert result.status == "active"

    @pytest.mark.asyncio
    async def test_create_listing_api_error(
        self,
        client: MercadoLibreClient,
        listing_request: MLListingRequest,
    ) -> None:
        """Wraps errors in MercadoLibreError with status code and ML error code."""
        error_body: dict[str, object] = {
            "message": "Invalid category",
            "error": "validation_error",
            "status": 400,
        }
        mock_resp = _make_response(400, error_body)
        mock_request = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.request = mock_request
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(MercadoLibreError) as exc_info:
                await client.create_listing(listing_request)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_listing_retry_on_5xx(
        self,
        client: MercadoLibreClient,
        listing_request: MLListingRequest,
    ) -> None:
        """Retries with backoff on server errors (5xx)."""
        fail_resp = _make_response(500, {})
        ok_resp = _make_response(200, VALID_LISTING_RESPONSE)

        mock_request = AsyncMock(side_effect=[fail_resp, fail_resp, ok_resp])

        with (
            patch("httpx.AsyncClient") as mock_cls,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_http = AsyncMock()
            mock_http.request = mock_request
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.create_listing(listing_request)

        assert isinstance(result, MLListingResponse)
        assert mock_request.call_count == 3
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0].args[0] == _BACKOFF_BASE * (2**0)
        assert mock_sleep.call_args_list[1].args[0] == _BACKOFF_BASE * (2**1)

    @pytest.mark.asyncio
    async def test_create_listing_no_retry_on_4xx(
        self,
        client: MercadoLibreClient,
        listing_request: MLListingRequest,
    ) -> None:
        """Client errors (4xx, excluding 401) fail immediately without retry."""
        mock_resp = _make_response(400, {"error": "bad_request"})
        mock_request = AsyncMock(return_value=mock_resp)

        with (
            patch("httpx.AsyncClient") as mock_cls,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_http = AsyncMock()
            mock_http.request = mock_request
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(MercadoLibreError):
                await client.create_listing(listing_request)

        # 4xx should fail immediately — no retries, no sleep
        mock_sleep.assert_not_called()
        assert mock_request.call_count == 1


# ---------------------------------------------------------------------------
# update_listing
# ---------------------------------------------------------------------------


class TestUpdateListing:
    """Tests for MercadoLibreClient.update_listing."""

    @pytest.mark.asyncio
    async def test_update_listing_success(self, client: MercadoLibreClient) -> None:
        """Updates existing listing and returns typed MLListingResponse."""
        updated_payload = {**VALID_LISTING_RESPONSE, "price": 2800.0}
        mock_resp = _make_response(200, updated_payload)
        mock_request = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.request = mock_request
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.update_listing("MLA123456789", {"price": 2800.0})

        assert isinstance(result, MLListingResponse)
        assert result.price == 2800.0


# ---------------------------------------------------------------------------
# pause_listing
# ---------------------------------------------------------------------------


class TestPauseListing:
    """Tests for MercadoLibreClient.pause_listing."""

    @pytest.mark.asyncio
    async def test_pause_listing_success(self, client: MercadoLibreClient) -> None:
        """Pauses listing and returns typed MLListingResponse with paused status."""
        paused_payload = {**VALID_LISTING_RESPONSE, "status": "paused"}
        mock_resp = _make_response(200, paused_payload)
        mock_request = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.request = mock_request
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.pause_listing("MLA123456789")

        assert isinstance(result, MLListingResponse)
        assert result.status == "paused"


# ---------------------------------------------------------------------------
# upload_image
# ---------------------------------------------------------------------------


class TestUploadImage:
    """Tests for MercadoLibreClient.upload_image."""

    @pytest.mark.asyncio
    async def test_upload_image_success(self, client: MercadoLibreClient) -> None:
        """Returns ML picture ID on successful upload."""
        mock_resp = _make_response(200, VALID_MEDIA_RESPONSE)
        mock_request = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.request = mock_request
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.upload_image("https://cdn.example.com/img.jpg")

        assert result == "MEDIA-001"


# ---------------------------------------------------------------------------
# upload_video
# ---------------------------------------------------------------------------


class TestUploadVideo:
    """Tests for MercadoLibreClient.upload_video."""

    @pytest.mark.asyncio
    async def test_upload_video_success(self, client: MercadoLibreClient) -> None:
        """Returns ML video ID on successful upload."""
        video_response: dict[str, object] = {"id": "VIDEO-001", "status": "processed"}
        mock_resp = _make_response(200, video_response)
        mock_request = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.request = mock_request
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.upload_video("https://cdn.example.com/video.mp4")

        assert result == "VIDEO-001"


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


class TestTokenRefresh:
    """Tests for OAuth2 token refresh logic."""

    @pytest.mark.asyncio
    async def test_refresh_token_on_401(
        self,
        client: MercadoLibreClient,
        listing_request: MLListingRequest,
    ) -> None:
        """Auto-refreshes token on 401 and retries the original request."""
        unauthorized_resp = _make_response(401, {"message": "invalid_token"})
        ok_resp = _make_response(200, VALID_LISTING_RESPONSE)
        token_resp = _make_response(200, VALID_TOKEN_RESPONSE)

        # request mock: 1st call -> 401, 2nd call -> success (post handles refresh)
        mock_request = AsyncMock(side_effect=[unauthorized_resp, ok_resp])

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.request = mock_request
            mock_http.post = AsyncMock(return_value=token_resp)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.create_listing(listing_request)

        assert isinstance(result, MLListingResponse)
        assert result.id == "MLA123456789"

    @pytest.mark.asyncio
    async def test_refresh_token_failure(
        self,
        client: MercadoLibreClient,
        listing_request: MLListingRequest,
    ) -> None:
        """Raises MercadoLibreError if token refresh itself fails."""
        unauthorized_resp = _make_response(401, {"message": "invalid_token"})
        refresh_fail_resp = _make_response(400, {"error": "invalid_grant"})

        mock_request = AsyncMock(return_value=unauthorized_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.request = mock_request
            mock_http.post = AsyncMock(return_value=refresh_fail_resp)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(MercadoLibreError) as exc_info:
                await client.create_listing(listing_request)

        assert "token refresh" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# Backoff and auth header
# ---------------------------------------------------------------------------


class TestRequestWithRetry:
    """Tests for _request_with_retry internals."""

    @pytest.mark.asyncio
    async def test_request_with_retry_backoff(
        self,
        client: MercadoLibreClient,
        listing_request: MLListingRequest,
    ) -> None:
        """Exponential backoff delays are correct: 5s, 10s, 20s."""
        fail_resp = _make_response(500, {})
        mock_request = AsyncMock(return_value=fail_resp)

        with (
            patch("httpx.AsyncClient") as mock_cls,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_http = AsyncMock()
            mock_http.request = mock_request
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(MercadoLibreError):
                await client.create_listing(listing_request)

        assert mock_sleep.call_count == _MAX_RETRIES
        for i in range(_MAX_RETRIES):
            assert mock_sleep.call_args_list[i].args[0] == _BACKOFF_BASE * (2**i)

    @pytest.mark.asyncio
    async def test_auth_header_uses_access_token(
        self,
        client: MercadoLibreClient,
        listing_request: MLListingRequest,
    ) -> None:
        """Authorization header uses Bearer <access_token>."""
        mock_resp = _make_response(200, VALID_LISTING_RESPONSE)
        mock_request = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.request = mock_request
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await client.create_listing(listing_request)

        # Verify the client was created with the correct Authorization header
        call_kwargs = mock_cls.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer test-access-token"
