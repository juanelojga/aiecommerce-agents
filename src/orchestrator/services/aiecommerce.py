"""AIEcommerce API client.

Wraps all outbound HTTP calls to the aiecommerce platform behind
an async interface so the transport can be swapped or mocked easily.
"""

import logging

import httpx

from orchestrator.core.config import Settings

logger = logging.getLogger(__name__)


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
