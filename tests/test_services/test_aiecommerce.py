"""Tests for AIEcommerceClient inventory and product-spec methods."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from orchestrator.core.config import Settings
from orchestrator.core.exceptions import APIClientError
from orchestrator.schemas.inventory import InventoryItem, InventoryResponse, ProductSpecs
from orchestrator.services.aiecommerce import _BACKOFF_BASE, _MAX_RETRIES, AIEcommerceClient

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

VALID_ITEM: dict[str, object] = {
    "id": 1,
    "sku": "CPU-001",
    "name": "Ryzen 9 7950X",
    "category": "cpu",
    "price": 699.99,
    "available_quantity": 5,
    "is_active": True,
}

VALID_INVENTORY_PAYLOAD: dict[str, object] = {
    "count": 1,
    "results": [VALID_ITEM],
}

VALID_SPECS_PAYLOAD: dict[str, object] = {
    "id": 1,
    "sku": "CPU-001",
    "socket": "AM5",
    "tdp": 170,
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
# get_inventory
# ---------------------------------------------------------------------------


class TestGetInventory:
    """Tests for AIEcommerceClient.get_inventory."""

    @pytest.mark.asyncio
    async def test_get_inventory_success(self, client: AIEcommerceClient) -> None:
        """Returns a typed InventoryResponse on a successful API call."""
        mock_resp = _make_response(200, VALID_INVENTORY_PAYLOAD)
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_inventory()

        assert isinstance(result, InventoryResponse)
        assert result.count == 1
        assert len(result.results) == 1
        assert isinstance(result.results[0], InventoryItem)
        assert result.results[0].sku == "CPU-001"

    @pytest.mark.asyncio
    async def test_get_inventory_with_category_filter(self, client: AIEcommerceClient) -> None:
        """Passes category as a query parameter when provided."""
        mock_resp = _make_response(200, VALID_INVENTORY_PAYLOAD)
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await client.get_inventory(category="cpu")

        _, call_kwargs = mock_get.call_args
        params = call_kwargs.get("params", {})
        assert params.get("category") == "cpu"

    @pytest.mark.asyncio
    async def test_get_inventory_active_and_stock_filters(self, client: AIEcommerceClient) -> None:
        """Passes is_active and in_stock query params when flags are True."""
        mock_resp = _make_response(200, VALID_INVENTORY_PAYLOAD)
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await client.get_inventory(active_only=True, in_stock_only=True)

        _, call_kwargs = mock_get.call_args
        params = call_kwargs.get("params", {})
        assert params.get("is_active") == "true"
        assert params.get("in_stock") == "true"

    @pytest.mark.asyncio
    async def test_get_inventory_no_filters_when_disabled(self, client: AIEcommerceClient) -> None:
        """Omits is_active and in_stock params when the flags are False."""
        mock_resp = _make_response(200, VALID_INVENTORY_PAYLOAD)
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await client.get_inventory(active_only=False, in_stock_only=False)

        _, call_kwargs = mock_get.call_args
        # params should be None (no filters) or not contain is_active/in_stock
        params = call_kwargs.get("params") or {}
        assert "is_active" not in params
        assert "in_stock" not in params

    @pytest.mark.asyncio
    async def test_get_inventory_api_error_raises(self, client: AIEcommerceClient) -> None:
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
                await client.get_inventory()

        # asyncio.sleep should have been called for each retry
        assert mock_sleep.call_count == _MAX_RETRIES

    @pytest.mark.asyncio
    async def test_get_inventory_retry_on_failure(self, client: AIEcommerceClient) -> None:
        """Retries with exponential backoff and succeeds on the final attempt."""
        fail_resp = _make_response(500, {})
        ok_resp = _make_response(200, VALID_INVENTORY_PAYLOAD)

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

            result = await client.get_inventory()

        assert isinstance(result, InventoryResponse)
        assert mock_get.call_count == 3
        # Verify backoff delays: 5s, 10s
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0].args[0] == _BACKOFF_BASE * (2**0)
        assert mock_sleep.call_args_list[1].args[0] == _BACKOFF_BASE * (2**1)


# ---------------------------------------------------------------------------
# get_product_specs
# ---------------------------------------------------------------------------


class TestGetProductSpecs:
    """Tests for AIEcommerceClient.get_product_specs."""

    @pytest.mark.asyncio
    async def test_get_product_specs_success(self, client: AIEcommerceClient) -> None:
        """Returns a typed ProductSpecs on a successful API call."""
        mock_resp = _make_response(200, VALID_SPECS_PAYLOAD)
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_product_specs(1)

        assert isinstance(result, ProductSpecs)
        assert result.id == 1
        assert result.sku == "CPU-001"
        assert result.socket == "AM5"

    @pytest.mark.asyncio
    async def test_get_product_specs_calls_correct_path(self, client: AIEcommerceClient) -> None:
        """Calls the correct API path with the given product_id."""
        mock_resp = _make_response(200, VALID_SPECS_PAYLOAD)
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await client.get_product_specs(42)

        call_args, _ = mock_get.call_args
        assert call_args[0] == "/api/v1/agent/product/42/specs/"

    @pytest.mark.asyncio
    async def test_get_product_specs_not_found(self, client: AIEcommerceClient) -> None:
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
                await client.get_product_specs(999)

        # 404 is a client error — no retries, so sleep must not be called
        mock_sleep.assert_not_called()
        assert mock_get.call_count == 1

    @pytest.mark.asyncio
    async def test_get_product_specs_network_error_retries(self, client: AIEcommerceClient) -> None:
        """Network errors are retried up to _MAX_RETRIES times."""
        network_error = httpx.ConnectError("connection refused")
        ok_resp = _make_response(200, VALID_SPECS_PAYLOAD)

        mock_get = AsyncMock(side_effect=[network_error, ok_resp])

        with (
            patch("httpx.AsyncClient") as mock_cls,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_http = AsyncMock()
            mock_http.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await client.get_product_specs(1)

        assert isinstance(result, ProductSpecs)
        assert mock_get.call_count == 2
        assert mock_sleep.call_count == 1
