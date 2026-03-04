"""Tests for the custom exception hierarchy and FastAPI exception handlers."""

from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrator.core.exceptions import (
    APIClientError,
    CompatibilityError,
    InventoryError,
    OrchestratorError,
    TowerNotFoundError,
    UniquenessError,
)
from orchestrator.main import create_app


class TestOrchestratorErrorIsBase:
    """All custom exceptions must inherit from OrchestratorError."""

    def test_api_client_error_is_orchestrator_error(self) -> None:
        """APIClientError inherits from OrchestratorError."""
        assert issubclass(APIClientError, OrchestratorError)

    def test_inventory_error_is_orchestrator_error(self) -> None:
        """InventoryError inherits from OrchestratorError."""
        assert issubclass(InventoryError, OrchestratorError)

    def test_compatibility_error_is_orchestrator_error(self) -> None:
        """CompatibilityError inherits from OrchestratorError."""
        assert issubclass(CompatibilityError, OrchestratorError)

    def test_uniqueness_error_is_orchestrator_error(self) -> None:
        """UniquenessError inherits from OrchestratorError."""
        assert issubclass(UniquenessError, OrchestratorError)

    def test_tower_not_found_error_is_orchestrator_error(self) -> None:
        """TowerNotFoundError inherits from OrchestratorError."""
        assert issubclass(TowerNotFoundError, OrchestratorError)

    def test_orchestrator_error_inherits_from_exception(self) -> None:
        """OrchestratorError itself is a subclass of the built-in Exception."""
        assert issubclass(OrchestratorError, Exception)

    def test_exception_stores_message(self) -> None:
        """Raising OrchestratorError stores the message on the instance."""
        exc = OrchestratorError("something went wrong")
        assert exc.message == "something went wrong"
        assert str(exc) == "something went wrong"


class TestExceptionHandlerReturnsJson:
    """FastAPI exception handler must return {"detail": "..."} with the mapped status code."""

    @pytest.fixture
    def app_with_trigger(self) -> FastAPI:
        """Return the app with test routes that raise each OrchestratorError subclass."""
        application = create_app()

        _routes: list[tuple[str, type[OrchestratorError], str]] = [
            ("/_test/tower-not-found", TowerNotFoundError, "tower abc123 not found"),
            ("/_test/api-client-error", APIClientError, "upstream API timeout"),
            ("/_test/compatibility-error", CompatibilityError, "incompatible components"),
            ("/_test/uniqueness-error", UniquenessError, "no unique build found"),
            ("/_test/inventory-error", InventoryError, "inventory unavailable"),
        ]

        def _make_handler(
            exc_cls: type[OrchestratorError], msg: str
        ) -> Callable[[], Coroutine[Any, Any, None]]:
            async def _handler() -> None:
                raise exc_cls(msg)

            return _handler

        for path, exc_cls, msg in _routes:
            application.add_api_route(path, _make_handler(exc_cls, msg))

        return application

    @pytest.mark.asyncio
    async def test_tower_not_found_returns_404(self, app_with_trigger: FastAPI) -> None:
        """TowerNotFoundError produces a 404 JSON response."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_trigger),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/_test/tower-not-found")

        assert response.status_code == 404
        assert response.json() == {"detail": "tower abc123 not found"}

    @pytest.mark.asyncio
    async def test_api_client_error_returns_502(self, app_with_trigger: FastAPI) -> None:
        """APIClientError produces a 502 JSON response."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_trigger),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/_test/api-client-error")

        assert response.status_code == 502
        assert response.json() == {"detail": "upstream API timeout"}

    @pytest.mark.asyncio
    async def test_compatibility_error_returns_422(self, app_with_trigger: FastAPI) -> None:
        """CompatibilityError produces a 422 JSON response."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_trigger),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/_test/compatibility-error")

        assert response.status_code == 422
        assert response.json() == {"detail": "incompatible components"}

    @pytest.mark.asyncio
    async def test_uniqueness_error_returns_409(self, app_with_trigger: FastAPI) -> None:
        """UniquenessError produces a 409 JSON response."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_trigger),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/_test/uniqueness-error")

        assert response.status_code == 409
        assert response.json() == {"detail": "no unique build found"}

    @pytest.mark.asyncio
    async def test_inventory_error_returns_503(self, app_with_trigger: FastAPI) -> None:
        """InventoryError produces a 503 JSON response."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_trigger),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/_test/inventory-error")

        assert response.status_code == 503
        assert response.json() == {"detail": "inventory unavailable"}

    def test_exception_handler_returns_json_with_sync_client(
        self, app_with_trigger: FastAPI
    ) -> None:
        """Synchronous smoke-test: handler returns {"detail": "..."} format."""
        client = TestClient(app_with_trigger, raise_server_exceptions=False)
        response = client.get("/_test/tower-not-found")
        assert response.status_code == 404
        body = response.json()
        assert "detail" in body
        assert body["detail"] == "tower abc123 not found"
