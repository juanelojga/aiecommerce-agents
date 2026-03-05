"""Tests for the Bundle Creator LangGraph node.

Covers FR-2.1 through FR-2.3 and FR-6.2:

- Home tier: basic keyboard, mouse, monitor (cheapest).
- Business tier: ergonomic keyboard, mouse, standard monitor (balanced).
- Gaming tier: mechanical KB, gaming mouse, ≥144 Hz monitor, speakers (premium).
- Empty builds return completed with empty bundles.
- BundleRepository.create() called per build.
- ComponentAuditRepository.record_bundle_usage() updated for peripheral SKUs.
- Missing peripheral category handled gracefully per tier.
- Multiple tiers create separate bundles.
- API errors return failed status.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.core.exceptions import APIClientError
from orchestrator.graph.nodes.bundle_creator import (
    _append_tier_error,
    _build_peripheral_skus,
    bundle_creator_node,
)
from orchestrator.graph.state import GraphState
from orchestrator.schemas.bundle import PeripheralCategory, PeripheralSelection
from orchestrator.schemas.product import (
    ComponentCategory,
    ProductDetail,
    ProductListItem,
    ProductListResponse,
)

# ---------------------------------------------------------------------------
# Test fixture helpers
# ---------------------------------------------------------------------------


def _make_list_item(
    product_id: int,
    price: float,
    category: ComponentCategory,
    sku: str | None = None,
) -> ProductListItem:
    """Build a minimal :class:`ProductListItem` for testing."""
    return ProductListItem(
        id=product_id,
        code=f"CODE-{product_id}",
        sku=sku or f"SKU-{product_id}",
        normalized_name=f"Product {product_id}",
        price=price,
        category=category,
        total_available_stock=10,
    )


def _make_detail(
    product_id: int,
    price: float,
    category: ComponentCategory,
    specs: dict[str, object] | None = None,
) -> ProductDetail:
    """Build a minimal :class:`ProductDetail` for testing."""
    return ProductDetail(
        id=product_id,
        code=f"CODE-{product_id}",
        sku=f"SKU-{product_id}",
        normalized_name=f"Product {product_id}",
        price=price,
        category=category,
        specs=specs or {},
    )


def _build_peripheral_inventory(
    *,
    include_speakers: bool = True,
    monitor_specs: dict[str, object] | None = None,
    keyboard_items: list[ProductListItem] | None = None,
    mouse_items: list[ProductListItem] | None = None,
    monitor_items: list[ProductListItem] | None = None,
    speakers_items: list[ProductListItem] | None = None,
) -> tuple[dict[str, list[ProductListItem]], dict[int, ProductDetail]]:
    """Build a peripheral inventory and specs cache for testing.

    Args:
        include_speakers: Whether to include speakers in the inventory.
        monitor_specs: Extra specs to apply to all monitors.
        keyboard_items: Override keyboard items.
        mouse_items: Override mouse items.
        monitor_items: Override monitor items.
        speakers_items: Override speakers items.

    Returns:
        Tuple of (peripheral_inventory, specs_cache).
    """
    items: list[ProductListItem] = []
    details: list[ProductDetail] = []

    # Keyboards
    if keyboard_items is not None:
        items.extend(keyboard_items)
        for it in keyboard_items:
            details.append(_make_detail(it.id, it.price, it.category))
    else:
        kb = [
            _make_list_item(1, 25.0, ComponentCategory.KEYBOARD, sku="KB-BASIC"),
            _make_list_item(2, 75.0, ComponentCategory.KEYBOARD, sku="KB-ERGO"),
            _make_list_item(3, 150.0, ComponentCategory.KEYBOARD, sku="KB-MECH"),
        ]
        items.extend(kb)
        for it in kb:
            details.append(_make_detail(it.id, it.price, it.category))

    # Mice
    if mouse_items is not None:
        items.extend(mouse_items)
        for it in mouse_items:
            details.append(_make_detail(it.id, it.price, it.category))
    else:
        mice = [
            _make_list_item(4, 15.0, ComponentCategory.MOUSE, sku="MOUSE-BASIC"),
            _make_list_item(5, 50.0, ComponentCategory.MOUSE, sku="MOUSE-ERGO"),
            _make_list_item(6, 120.0, ComponentCategory.MOUSE, sku="MOUSE-GAMING"),
        ]
        items.extend(mice)
        for it in mice:
            details.append(_make_detail(it.id, it.price, it.category))

    # Monitors
    if monitor_items is not None:
        items.extend(monitor_items)
        for it in monitor_items:
            mon_specs = monitor_specs or {}
            details.append(_make_detail(it.id, it.price, it.category, specs=mon_specs))
    else:
        monitors = [
            _make_list_item(7, 150.0, ComponentCategory.MONITOR, sku="MON-BASIC"),
            _make_list_item(8, 350.0, ComponentCategory.MONITOR, sku="MON-STD"),
            _make_list_item(9, 600.0, ComponentCategory.MONITOR, sku="MON-144HZ"),
        ]
        items.extend(monitors)
        for mon in monitors:
            mon_specs = monitor_specs or {}
            # Give the 144Hz monitor the appropriate spec tag.
            if mon.sku == "MON-144HZ":
                mon_specs = {**mon_specs, "refresh_rate": "144hz"}
            details.append(_make_detail(mon.id, mon.price, mon.category, specs=mon_specs))

    # Speakers
    if include_speakers:
        if speakers_items is not None:
            items.extend(speakers_items)
            for it in speakers_items:
                details.append(_make_detail(it.id, it.price, it.category))
        else:
            spk = [
                _make_list_item(10, 40.0, ComponentCategory.SPEAKERS, sku="SPK-BASIC"),
                _make_list_item(11, 200.0, ComponentCategory.SPEAKERS, sku="SPK-PREMIUM"),
            ]
            items.extend(spk)
            for it in spk:
                details.append(_make_detail(it.id, it.price, it.category))

    inventory: dict[str, list[ProductListItem]] = {}
    for item in items:
        inventory.setdefault(item.category.value, []).append(item)

    specs_cache: dict[int, ProductDetail] = {d.id: d for d in details}
    return inventory, specs_cache


def _make_api_client_mock(
    inventory: dict[str, list[ProductListItem]],
    specs_cache: dict[int, ProductDetail],
) -> Any:
    """Return a mocked :class:`AIEcommerceClient`."""
    mock = MagicMock()

    async def _list_products(
        category: str | None = None,
        active_only: bool = True,
        has_stock: bool = True,
    ) -> ProductListResponse:
        results = inventory.get(category or "", []) if category else []
        return ProductListResponse(count=len(results), results=results)

    async def _get_detail(product_id: int) -> ProductDetail:
        return specs_cache[product_id]

    mock.list_products = _list_products
    mock.get_product_detail = _get_detail
    return mock


def _make_session_mock() -> tuple[Any, Any, Any]:
    """Return (mock_session, mock_bundle_repo, mock_audit_repo) mocks."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_bundle_repo = AsyncMock()
    mock_bundle_repo.create = AsyncMock()

    mock_audit_repo = AsyncMock()
    mock_audit_repo.record_bundle_usage = AsyncMock()

    return mock_session, mock_bundle_repo, mock_audit_repo


def _make_completed_tower_build(
    tier: str = "Home",
    bundle_hash: str = "a" * 64,
    total_price: float = 599.99,
) -> dict[str, object]:
    """Create a minimal completed build dict as produced by the Inventory Architect."""
    return {
        "tier": tier,
        "bundle_hash": bundle_hash,
        "total_price": total_price,
    }


def _configure_session_factory(mock_factory: Any) -> None:
    """Configure the async_session_factory mock as an async context manager."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)


def _build_node_mocks(
    inventory: dict[str, list[ProductListItem]] | None = None,
    specs_cache: dict[int, ProductDetail] | None = None,
) -> tuple[Any, Any, Any]:
    """Build all mocks needed to test the node end-to-end.

    Returns:
        Tuple of (mock_api_client, mock_bundle_repo, mock_audit_repo).
    """
    if inventory is None or specs_cache is None:
        inv, cache = _build_peripheral_inventory()
        inventory = inventory or inv
        specs_cache = specs_cache or cache

    mock_api = _make_api_client_mock(inventory, specs_cache)
    _, mock_bundle_repo, mock_audit_repo = _make_session_mock()

    return mock_api, mock_bundle_repo, mock_audit_repo


def _extract_peripheral_skus(bundle: dict[str, object]) -> dict[str, str]:
    """Extract a category → SKU mapping from a serialised bundle dict.

    Args:
        bundle: A serialised BundleBuild dict.

    Returns:
        Mapping of peripheral category value to its SKU.
    """
    peripherals: list[dict[str, object]] = bundle["peripherals"]  # type: ignore[assignment]
    return {str(p["category"]): str(p["sku"]) for p in peripherals}


# ---------------------------------------------------------------------------
# Unit tests: helper functions
# ---------------------------------------------------------------------------


class TestBuildPeripheralSkus:
    """Tests for _build_peripheral_skus."""

    def test_maps_category_to_sku(self) -> None:
        """Each peripheral selection's category becomes the key."""
        detail = _make_detail(1, 25.0, ComponentCategory.KEYBOARD)
        selections = [
            PeripheralSelection(
                sku="KB-001",
                normalized_name="Keyboard",
                category=PeripheralCategory.KEYBOARD,
                price=25.0,
                specs=detail,
            ),
            PeripheralSelection(
                sku="MS-001",
                normalized_name="Mouse",
                category=PeripheralCategory.MOUSE,
                price=15.0,
                specs=_make_detail(2, 15.0, ComponentCategory.MOUSE),
            ),
        ]
        result = _build_peripheral_skus(selections)
        assert result == {"keyboard": "KB-001", "mouse": "MS-001"}

    def test_empty_selections(self) -> None:
        """Empty selection list returns empty dict."""
        result = _build_peripheral_skus([])
        assert result == {}


class TestAppendTierError:
    """Tests for _append_tier_error."""

    def test_formats_error_message(self) -> None:
        """Error message includes tier name and detail."""
        errors: list[str] = []
        _append_tier_error(errors, "Home", "No keyboards available")
        assert len(errors) == 1
        assert "Home" in errors[0]
        assert "No keyboards available" in errors[0]


# ---------------------------------------------------------------------------
# Integration tests: bundle_creator_node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bundle_creator_home_tier() -> None:
    """Home tier selects cheapest peripherals (keyboard, mouse, monitor)."""
    inventory, specs_cache = _build_peripheral_inventory()
    mock_api, mock_bundle_repo, mock_audit_repo = _build_node_mocks(inventory, specs_cache)

    state = GraphState(completed_builds=[_make_completed_tower_build("Home")])

    with (
        patch(
            "orchestrator.graph.nodes.bundle_creator.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.bundle_creator.BundleRepository",
            return_value=mock_bundle_repo,
        ),
        patch(
            "orchestrator.graph.nodes.bundle_creator.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch("orchestrator.graph.nodes.bundle_creator.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await bundle_creator_node(state)

    assert result["run_status"] == "completed"
    assert len(result["completed_bundles"]) == 1  # type: ignore[arg-type]
    bundle = result["completed_bundles"][0]  # type: ignore[index]
    assert bundle["tier"] == "Home"
    # Home tier picks cheapest: KB-BASIC (25), MOUSE-BASIC (15), MON-BASIC (150).
    peripheral_skus = _extract_peripheral_skus(bundle)
    assert peripheral_skus["keyboard"] == "KB-BASIC"
    assert peripheral_skus["mouse"] == "MOUSE-BASIC"
    assert peripheral_skus["monitor"] == "MON-BASIC"
    # Home tier has no speakers.
    assert "speakers" not in peripheral_skus


@pytest.mark.asyncio
async def test_bundle_creator_business_tier() -> None:
    """Business tier selects balanced (median) peripherals."""
    inventory, specs_cache = _build_peripheral_inventory()
    mock_api, mock_bundle_repo, mock_audit_repo = _build_node_mocks(inventory, specs_cache)

    state = GraphState(
        completed_builds=[_make_completed_tower_build("Business", bundle_hash="b" * 64)]
    )

    with (
        patch(
            "orchestrator.graph.nodes.bundle_creator.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.bundle_creator.BundleRepository",
            return_value=mock_bundle_repo,
        ),
        patch(
            "orchestrator.graph.nodes.bundle_creator.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch("orchestrator.graph.nodes.bundle_creator.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await bundle_creator_node(state)

    assert result["run_status"] == "completed"
    bundle = result["completed_bundles"][0]  # type: ignore[index]
    assert bundle["tier"] == "Business"
    # Business tier picks median: KB-ERGO (75), MOUSE-ERGO (50), MON-STD (350).
    peripheral_skus = _extract_peripheral_skus(bundle)
    assert peripheral_skus["keyboard"] == "KB-ERGO"
    assert peripheral_skus["mouse"] == "MOUSE-ERGO"
    assert peripheral_skus["monitor"] == "MON-STD"


@pytest.mark.asyncio
async def test_bundle_creator_gaming_tier() -> None:
    """Gaming tier selects premium peripherals including speakers."""
    inventory, specs_cache = _build_peripheral_inventory()
    mock_api, mock_bundle_repo, mock_audit_repo = _build_node_mocks(inventory, specs_cache)

    state = GraphState(
        completed_builds=[_make_completed_tower_build("Gaming", bundle_hash="c" * 64)]
    )

    with (
        patch(
            "orchestrator.graph.nodes.bundle_creator.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.bundle_creator.BundleRepository",
            return_value=mock_bundle_repo,
        ),
        patch(
            "orchestrator.graph.nodes.bundle_creator.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch("orchestrator.graph.nodes.bundle_creator.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await bundle_creator_node(state)

    assert result["run_status"] == "completed"
    bundle = result["completed_bundles"][0]  # type: ignore[index]
    assert bundle["tier"] == "Gaming"
    # Gaming tier picks premium: KB-MECH (150), MOUSE-GAMING (120),
    # MON-144HZ (600), SPK-PREMIUM (200).
    peripheral_skus = _extract_peripheral_skus(bundle)
    assert peripheral_skus["keyboard"] == "KB-MECH"
    assert peripheral_skus["mouse"] == "MOUSE-GAMING"
    assert peripheral_skus["monitor"] == "MON-144HZ"
    assert peripheral_skus["speakers"] == "SPK-PREMIUM"


@pytest.mark.asyncio
async def test_bundle_creator_empty_builds() -> None:
    """Returns completed with empty bundles when no builds exist."""
    state = GraphState(completed_builds=[])
    result = await bundle_creator_node(state)

    assert result["run_status"] == "completed"
    assert result["completed_bundles"] == []
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_bundle_creator_persists_bundle() -> None:
    """BundleRepository.create() is called once per build."""
    inventory, specs_cache = _build_peripheral_inventory()
    mock_api, mock_bundle_repo, mock_audit_repo = _build_node_mocks(inventory, specs_cache)

    state = GraphState(completed_builds=[_make_completed_tower_build("Home")])

    with (
        patch(
            "orchestrator.graph.nodes.bundle_creator.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.bundle_creator.BundleRepository",
            return_value=mock_bundle_repo,
        ),
        patch(
            "orchestrator.graph.nodes.bundle_creator.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch("orchestrator.graph.nodes.bundle_creator.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await bundle_creator_node(state)

    assert result["run_status"] == "completed"
    mock_bundle_repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_bundle_creator_records_audit() -> None:
    """ComponentAuditRepository.record_bundle_usage() called for peripheral SKUs."""
    inventory, specs_cache = _build_peripheral_inventory()
    mock_api, mock_bundle_repo, mock_audit_repo = _build_node_mocks(inventory, specs_cache)

    state = GraphState(completed_builds=[_make_completed_tower_build("Home")])

    with (
        patch(
            "orchestrator.graph.nodes.bundle_creator.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.bundle_creator.BundleRepository",
            return_value=mock_bundle_repo,
        ),
        patch(
            "orchestrator.graph.nodes.bundle_creator.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch("orchestrator.graph.nodes.bundle_creator.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await bundle_creator_node(state)

    assert result["run_status"] == "completed"
    mock_audit_repo.record_bundle_usage.assert_called_once()
    # Verify the SKUs passed include peripherals (Home = 3 peripherals).
    call_args = mock_audit_repo.record_bundle_usage.call_args[0][0]
    assert len(call_args) == 3  # keyboard, mouse, monitor


@pytest.mark.asyncio
async def test_bundle_creator_missing_peripheral_error() -> None:
    """Handles missing peripheral category gracefully, skipping the tier."""
    # Build inventory with no monitors to trigger InventoryError.
    inventory, specs_cache = _build_peripheral_inventory(
        monitor_items=[],
    )
    # Remove monitor key entirely so PeripheralSelector raises.
    inventory.pop(ComponentCategory.MONITOR.value, None)

    mock_api, mock_bundle_repo, mock_audit_repo = _build_node_mocks(inventory, specs_cache)

    state = GraphState(completed_builds=[_make_completed_tower_build("Home")])

    with (
        patch(
            "orchestrator.graph.nodes.bundle_creator.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.bundle_creator.BundleRepository",
            return_value=mock_bundle_repo,
        ),
        patch(
            "orchestrator.graph.nodes.bundle_creator.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch("orchestrator.graph.nodes.bundle_creator.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await bundle_creator_node(state)

    # Tier was skipped; no bundles produced, but errors reported.
    assert result["run_status"] == "failed"
    assert len(result["errors"]) > 0  # type: ignore[arg-type]
    assert result["completed_bundles"] == []
    errors: list[str] = result["errors"]  # type: ignore[assignment]
    assert any("monitor" in e.lower() for e in errors)


@pytest.mark.asyncio
async def test_bundle_creator_multiple_tiers() -> None:
    """Creates separate bundles for each completed build."""
    inventory, specs_cache = _build_peripheral_inventory()
    mock_api, mock_bundle_repo, mock_audit_repo = _build_node_mocks(inventory, specs_cache)

    state = GraphState(
        completed_builds=[
            _make_completed_tower_build("Home", bundle_hash="a" * 64),
            _make_completed_tower_build("Gaming", bundle_hash="b" * 64),
        ]
    )

    with (
        patch(
            "orchestrator.graph.nodes.bundle_creator.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.bundle_creator.BundleRepository",
            return_value=mock_bundle_repo,
        ),
        patch(
            "orchestrator.graph.nodes.bundle_creator.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch("orchestrator.graph.nodes.bundle_creator.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await bundle_creator_node(state)

    assert result["run_status"] == "completed"
    bundles: list[dict[str, object]] = result["completed_bundles"]  # type: ignore[assignment]
    assert len(bundles) == 2
    tiers = {b["tier"] for b in bundles}
    assert tiers == {"Home", "Gaming"}

    # Verify each bundle has a distinct bundle_id.
    bundle_ids = {b["bundle_id"] for b in bundles}
    assert len(bundle_ids) == 2

    # BundleRepository.create called twice.
    assert mock_bundle_repo.create.call_count == 2


@pytest.mark.asyncio
async def test_bundle_creator_api_error() -> None:
    """Returns error state on API failure."""
    mock_api = MagicMock()
    mock_api.list_products = AsyncMock(side_effect=APIClientError("Connection refused"))

    state = GraphState(completed_builds=[_make_completed_tower_build("Home")])

    with (
        patch(
            "orchestrator.graph.nodes.bundle_creator.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch("orchestrator.graph.nodes.bundle_creator.async_session_factory"),
    ):
        result = await bundle_creator_node(state)

    assert result["run_status"] == "failed"
    assert len(result["errors"]) > 0  # type: ignore[arg-type]
    assert result["completed_bundles"] == []
