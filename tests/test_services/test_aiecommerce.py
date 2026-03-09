"""Tests for AIEcommerceClient product list and product detail methods."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from orchestrator.core.config import Settings
from orchestrator.core.exceptions import APIClientError
from orchestrator.schemas.product import (
    ComponentCategory,
    ProductDetail,
    ProductListItem,
    ProductListResponse,
)
from orchestrator.services.aiecommerce import _BACKOFF_BASE, _MAX_RETRIES, AIEcommerceClient

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

VALID_ITEM: dict[str, object] = {
    "id": 1,
    "code": "PROD-001",
    "sku": "CPU-001",
    "normalized_name": "Ryzen 9 7950X",
    "category": "cpu",
    "price": 699.99,
    "is_active": True,
    "total_available_stock": 5,
}

VALID_LIST_PAYLOAD: dict[str, object] = {
    "count": 1,
    "results": [VALID_ITEM],
}

VALID_DETAIL_PAYLOAD: dict[str, object] = {
    "id": 1,
    "code": "PROD-001",
    "sku": "CPU-001",
    "normalized_name": "Ryzen 9 7950X",
    "price": 699.99,
    "category": "cpu",
    "specs": {"socket": "AM5", "tdp": 170},
}


@pytest.fixture
def client() -> AIEcommerceClient:
    """Return a client configured with dummy settings."""
    settings = Settings(
        AIECOMMERCE_API_URL="https://api.example.com",
        AIECOMMERCE_API_KEY="test-key",
    )
    return AIEcommerceClient(settings)


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
# list_products
# ---------------------------------------------------------------------------


class TestListProducts:
    """Tests for AIEcommerceClient.list_products."""

    @pytest.mark.asyncio
    async def test_list_products_success(self, client: AIEcommerceClient) -> None:
        """Returns a typed ProductListResponse on a successful API call."""
        mock_resp = _make_response(200, VALID_LIST_PAYLOAD)
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.list_products()

        assert isinstance(result, ProductListResponse)
        assert result.count == 1
        assert len(result.results) == 1
        assert isinstance(result.results[0], ProductListItem)
        assert result.results[0].sku == "CPU-001"

    @pytest.mark.asyncio
    async def test_list_products_with_category_filter(self, client: AIEcommerceClient) -> None:
        """Passes the translated API category string as a query parameter."""
        mock_resp = _make_response(200, VALID_LIST_PAYLOAD)
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await client.list_products(category=ComponentCategory.CPU)

        _, call_kwargs = mock_get.call_args
        params = call_kwargs.get("params", {})
        assert params.get("category") == "PROCESADORES"

    @pytest.mark.asyncio
    async def test_list_products_active_and_stock_filters(self, client: AIEcommerceClient) -> None:
        """Passes is_active and has_stock query params when flags are True."""
        mock_resp = _make_response(200, VALID_LIST_PAYLOAD)
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await client.list_products(active_only=True, has_stock=True)

        _, call_kwargs = mock_get.call_args
        params = call_kwargs.get("params", {})
        assert params.get("is_active") == "true"
        assert params.get("has_stock") == "true"

    @pytest.mark.asyncio
    async def test_list_products_no_filters_when_disabled(self, client: AIEcommerceClient) -> None:
        """Omits is_active and has_stock params when the flags are False."""
        mock_resp = _make_response(200, VALID_LIST_PAYLOAD)
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await client.list_products(active_only=False, has_stock=False)

        _, call_kwargs = mock_get.call_args
        # params should be None (no filters) or not contain is_active/has_stock
        params = call_kwargs.get("params") or {}
        assert "is_active" not in params
        assert "has_stock" not in params

    @pytest.mark.asyncio
    async def test_list_products_api_error_raises(self, client: AIEcommerceClient) -> None:
        """Wraps 5xx HTTP errors in APIClientError after exhausting retries."""
        mock_resp = _make_response(500, {})
        mock_get = AsyncMock(return_value=mock_resp)

        with (
            patch("httpx.AsyncClient") as mock_cls,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(APIClientError):
                await client.list_products()

        # asyncio.sleep should have been called for each retry
        assert mock_sleep.call_count == _MAX_RETRIES

    @pytest.mark.asyncio
    async def test_list_products_retry_on_failure(self, client: AIEcommerceClient) -> None:
        """Retries with exponential backoff and succeeds on the final attempt."""
        fail_resp = _make_response(500, {})
        ok_resp = _make_response(200, VALID_LIST_PAYLOAD)

        # Fail twice, then succeed on third call
        mock_get = AsyncMock(side_effect=[fail_resp, fail_resp, ok_resp])

        with (
            patch("httpx.AsyncClient") as mock_cls,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.list_products()

        assert isinstance(result, ProductListResponse)
        assert mock_get.call_count == 3
        # Verify backoff delays: 5s, 10s
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0].args[0] == _BACKOFF_BASE * (2**0)
        assert mock_sleep.call_args_list[1].args[0] == _BACKOFF_BASE * (2**1)


# ---------------------------------------------------------------------------
# get_product_detail
# ---------------------------------------------------------------------------


class TestGetProductDetail:
    """Tests for AIEcommerceClient.get_product_detail."""

    @pytest.mark.asyncio
    async def test_get_product_detail_success(self, client: AIEcommerceClient) -> None:
        """Returns a typed ProductDetail on a successful API call."""
        mock_resp = _make_response(200, VALID_DETAIL_PAYLOAD)
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_product_detail(1)

        assert isinstance(result, ProductDetail)
        assert result.id == 1
        assert result.sku == "CPU-001"
        assert result.specs == {"socket": "AM5", "tdp": 170}

    @pytest.mark.asyncio
    async def test_get_product_detail_calls_correct_path(self, client: AIEcommerceClient) -> None:
        """Calls the correct API path with the given product_id."""
        mock_resp = _make_response(200, VALID_DETAIL_PAYLOAD)
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await client.get_product_detail(42)

        call_args, _ = mock_get.call_args
        assert call_args[0] == "/api/v1/products/42/"

    @pytest.mark.asyncio
    async def test_get_product_detail_not_found(self, client: AIEcommerceClient) -> None:
        """404 response raises APIClientError immediately (no retry)."""
        mock_resp = _make_response(404, {})
        mock_get = AsyncMock(return_value=mock_resp)

        with (
            patch("httpx.AsyncClient") as mock_cls,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(APIClientError):
                await client.get_product_detail(999)

        # 404 is a client error — no retries, so sleep must not be called
        mock_sleep.assert_not_called()
        assert mock_get.call_count == 1

    @pytest.mark.asyncio
    async def test_get_product_detail_network_error_retries(
        self, client: AIEcommerceClient
    ) -> None:
        """Network errors are retried up to _MAX_RETRIES times."""
        network_error = httpx.ConnectError("connection refused")
        ok_resp = _make_response(200, VALID_DETAIL_PAYLOAD)

        mock_get = AsyncMock(side_effect=[network_error, ok_resp])

        with (
            patch("httpx.AsyncClient") as mock_cls,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_product_detail(1)

        assert isinstance(result, ProductDetail)
        assert mock_get.call_count == 2
        assert mock_sleep.call_count == 1
