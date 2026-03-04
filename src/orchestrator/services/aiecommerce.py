"""AIEcommerce API client.

Wraps all outbound HTTP calls to the aiecommerce platform behind
an async interface so the transport can be swapped or mocked easily.
"""

import asyncio
import logging

import httpx

from orchestrator.core.config import Settings
from orchestrator.core.exceptions import APIClientError
from orchestrator.schemas.product import ProductDetail, ProductListResponse

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 5.0  # seconds


class AIEcommerceClient:
    """Async HTTP client for the aiecommerce API.

    Args:
        settings: Application settings containing the API URL and key.
    """

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.AIECOMMERCE_API_URL
        self._headers = {
            "Authorization": f"Bearer {settings.AIECOMMERCE_API_KEY}",
            "Content-Type": "application/json",
        }

    async def get(self, path: str) -> dict[str, object]:
        """Perform an authenticated GET request.

        Args:
            path: API path relative to the base URL (e.g., ``/products``).

        Returns:
            Parsed JSON response as a dictionary.
        """
        async with httpx.AsyncClient(base_url=self._base_url, headers=self._headers) as client:
            response = await client.get(path)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]

    async def _get_with_retry(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, object]:
        """Perform a GET request with exponential-backoff retry for transient errors.

        Client errors (4xx) are raised immediately without retrying. Server
        errors (5xx) and network errors are retried up to ``_MAX_RETRIES``
        times with exponential backoff starting at ``_BACKOFF_BASE`` seconds.

        Args:
            path: API path relative to the base URL.
            params: Optional query parameters to append to the request.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            APIClientError: If the request fails after all retries or immediately
                on a 4xx client error.
        """
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    base_url=self._base_url, headers=self._headers
                ) as client:
                    response = await client.get(path, params=params)
                    response.raise_for_status()
                    return response.json()  # type: ignore[no-any-return]
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                # Do not retry client errors (4xx)
                if exc.response.status_code < 500:
                    raise APIClientError(str(exc)) from exc
            except httpx.RequestError as exc:
                last_exc = exc

            if attempt < _MAX_RETRIES:
                delay = _BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "Request to %s failed (attempt %d/%d), retrying in %.0fs",
                    path,
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)

        raise APIClientError(str(last_exc)) from last_exc

    async def list_products(
        self,
        category: str | None = None,
        active_only: bool = True,
        has_stock: bool = True,
    ) -> ProductListResponse:
        """Fetch a paginated product list from the aiecommerce API.

        Calls ``GET /api/v1/products/`` with optional query parameters
        to filter results by category, active status, and stock availability.

        Args:
            category: Filter by component category (e.g. ``"cpu"``). When
                ``None`` no category filter is applied.
            active_only: When ``True`` only active items are returned.
            has_stock: When ``True`` only items with stock > 0 are returned.

        Returns:
            Typed :class:`ProductListResponse` containing paginated product list.

        Raises:
            APIClientError: If the API call fails after all retries.
        """
        params: dict[str, str] = {}
        if category is not None:
            params["category"] = category
        if active_only:
            params["is_active"] = "true"
        if has_stock:
            params["has_stock"] = "true"

        data = await self._get_with_retry(
            "/api/v1/products/",
            params=params if params else None,
        )
        return ProductListResponse.model_validate(data)

    async def get_product_detail(self, product_id: int) -> ProductDetail:
        """Fetch full product detail including specs, images, and stock.

        Calls ``GET /api/v1/products/{product_id}/``.

        Args:
            product_id: The product ID in the aiecommerce system.

        Returns:
            Typed :class:`ProductDetail` for the given product.

        Raises:
            APIClientError: If the API call fails after all retries or the
                product is not found (404).
        """
        data = await self._get_with_retry(f"/api/v1/products/{product_id}/")
        return ProductDetail.model_validate(data)
