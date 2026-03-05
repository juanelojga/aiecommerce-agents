"""Tests for the PeripheralSelector service."""

import pytest

from orchestrator.core.exceptions import InventoryError
from orchestrator.schemas.bundle import PeripheralCategory, PeripheralSelection
from orchestrator.schemas.product import ComponentCategory, ProductDetail, ProductListItem
from orchestrator.services.peripheral_selector import PeripheralSelector

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _make_item(
    product_id: int,
    price: float,
    category: ComponentCategory = ComponentCategory.KEYBOARD,
    sku: str | None = None,
) -> ProductListItem:
    """Create a minimal :class:`ProductListItem` for testing."""
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
    category: ComponentCategory = ComponentCategory.KEYBOARD,
    specs: dict[str, object] | None = None,
) -> ProductDetail:
    """Create a minimal :class:`ProductDetail` for testing."""
    return ProductDetail(
        id=product_id,
        code=f"CODE-{product_id}",
        sku=f"SKU-{product_id}",
        normalized_name=f"Product {product_id}",
        price=price,
        category=category,
        specs=specs or {},
    )


def _build_inventory_and_cache(
    items: list[ProductListItem],
    details: list[ProductDetail],
) -> tuple[dict[str, list[ProductListItem]], dict[int, ProductDetail]]:
    """Group items by category and build a specs cache from detail objects."""
    inventory: dict[str, list[ProductListItem]] = {}
    for item in items:
        inventory.setdefault(item.category.value, []).append(item)

    specs_cache: dict[int, ProductDetail] = {d.id: d for d in details}
    return inventory, specs_cache


# ---------------------------------------------------------------------------
# Home tier — cheapest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_home_cheapest() -> None:
    """Home tier picks cheapest peripheral per category."""
    items = [
        _make_item(1, 50.0, ComponentCategory.KEYBOARD),
        _make_item(2, 20.0, ComponentCategory.KEYBOARD),  # cheapest
        _make_item(3, 35.0, ComponentCategory.KEYBOARD),
        _make_item(4, 40.0, ComponentCategory.MOUSE),
        _make_item(5, 15.0, ComponentCategory.MOUSE),  # cheapest
        _make_item(6, 200.0, ComponentCategory.MONITOR),
        _make_item(7, 120.0, ComponentCategory.MONITOR),  # cheapest
    ]
    details = [_make_detail(i.id, i.price, i.category) for i in items]
    inventory, specs_cache = _build_inventory_and_cache(items, details)

    selector = PeripheralSelector()
    selections = await selector.select_peripherals("Home", inventory, specs_cache)

    assert len(selections) == 3
    prices = {s.category: s.price for s in selections}
    assert prices[PeripheralCategory.KEYBOARD] == 20.0
    assert prices[PeripheralCategory.MOUSE] == 15.0
    assert prices[PeripheralCategory.MONITOR] == 120.0


# ---------------------------------------------------------------------------
# Business tier — balanced (median)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_business_balanced() -> None:
    """Business tier picks mid-range peripherals."""
    # 3 keyboards: 10, 30, 50  → median index 1 → price 30
    items = [
        _make_item(1, 10.0, ComponentCategory.KEYBOARD),
        _make_item(2, 30.0, ComponentCategory.KEYBOARD),  # median
        _make_item(3, 50.0, ComponentCategory.KEYBOARD),
        _make_item(4, 20.0, ComponentCategory.MOUSE),
        _make_item(5, 40.0, ComponentCategory.MOUSE),  # median
        _make_item(6, 60.0, ComponentCategory.MOUSE),
        _make_item(7, 100.0, ComponentCategory.MONITOR),
        _make_item(8, 200.0, ComponentCategory.MONITOR),  # median
        _make_item(9, 300.0, ComponentCategory.MONITOR),
    ]
    details = [_make_detail(i.id, i.price, i.category) for i in items]
    inventory, specs_cache = _build_inventory_and_cache(items, details)

    selector = PeripheralSelector()
    selections = await selector.select_peripherals("Business", inventory, specs_cache)

    assert len(selections) == 3
    prices = {s.category: s.price for s in selections}
    assert prices[PeripheralCategory.KEYBOARD] == 30.0
    assert prices[PeripheralCategory.MOUSE] == 40.0
    assert prices[PeripheralCategory.MONITOR] == 200.0


# ---------------------------------------------------------------------------
# Gaming tier — premium
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_gaming_premium() -> None:
    """Gaming tier picks top-tier peripherals."""
    items = [
        _make_item(1, 50.0, ComponentCategory.KEYBOARD),
        _make_item(2, 150.0, ComponentCategory.KEYBOARD),  # most expensive
        _make_item(3, 30.0, ComponentCategory.MOUSE),
        _make_item(4, 120.0, ComponentCategory.MOUSE),  # most expensive
        # Monitor with 144hz tag so it passes the gaming filter
        _make_item(5, 300.0, ComponentCategory.MONITOR, sku="MON-300"),
        _make_item(6, 600.0, ComponentCategory.MONITOR, sku="MON-600"),  # most expensive
        _make_item(7, 80.0, ComponentCategory.SPEAKERS),
        _make_item(8, 200.0, ComponentCategory.SPEAKERS),  # most expensive
    ]
    # Give monitors 144hz tags so they survive the filter
    details = [
        _make_detail(i.id, i.price, i.category)
        for i in items
        if i.category != ComponentCategory.MONITOR
    ] + [
        _make_detail(5, 300.0, ComponentCategory.MONITOR, specs={"refresh_rate": "144hz"}),
        _make_detail(6, 600.0, ComponentCategory.MONITOR, specs={"refresh_rate": "144hz"}),
    ]
    inventory, specs_cache = _build_inventory_and_cache(items, details)

    selector = PeripheralSelector()
    selections = await selector.select_peripherals("Gaming", inventory, specs_cache)

    assert len(selections) == 4
    prices = {s.category: s.price for s in selections}
    assert prices[PeripheralCategory.KEYBOARD] == 150.0
    assert prices[PeripheralCategory.MOUSE] == 120.0
    assert prices[PeripheralCategory.MONITOR] == 600.0
    assert prices[PeripheralCategory.SPEAKERS] == 200.0


@pytest.mark.asyncio
async def test_gaming_requires_speakers() -> None:
    """Gaming tier includes speakers in the selection."""
    items = [
        _make_item(1, 100.0, ComponentCategory.KEYBOARD),
        _make_item(2, 80.0, ComponentCategory.MOUSE),
        _make_item(3, 300.0, ComponentCategory.MONITOR, sku="MON-1"),
        _make_item(4, 150.0, ComponentCategory.SPEAKERS),
    ]
    details = [
        _make_detail(i.id, i.price, i.category)
        for i in items
        if i.category != ComponentCategory.MONITOR
    ] + [
        _make_detail(3, 300.0, ComponentCategory.MONITOR, specs={"refresh_rate": "144hz"}),
    ]
    inventory, specs_cache = _build_inventory_and_cache(items, details)

    selector = PeripheralSelector()
    selections = await selector.select_peripherals("Gaming", inventory, specs_cache)

    categories = {s.category for s in selections}
    assert PeripheralCategory.SPEAKERS in categories


@pytest.mark.asyncio
async def test_home_no_speakers() -> None:
    """Home tier does not include speakers in the selection."""
    items = [
        _make_item(1, 20.0, ComponentCategory.KEYBOARD),
        _make_item(2, 15.0, ComponentCategory.MOUSE),
        _make_item(3, 100.0, ComponentCategory.MONITOR),
        _make_item(4, 50.0, ComponentCategory.SPEAKERS),
    ]
    details = [_make_detail(i.id, i.price, i.category) for i in items]
    inventory, specs_cache = _build_inventory_and_cache(items, details)

    selector = PeripheralSelector()
    selections = await selector.select_peripherals("Home", inventory, specs_cache)

    categories = {s.category for s in selections}
    assert PeripheralCategory.SPEAKERS not in categories
    assert len(selections) == 3


# ---------------------------------------------------------------------------
# Error case
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_category_raises() -> None:
    """Raises InventoryError when a required peripheral category has no stock."""
    # Provide keyboard and mouse, but omit monitor entirely.
    items = [
        _make_item(1, 20.0, ComponentCategory.KEYBOARD),
        _make_item(2, 15.0, ComponentCategory.MOUSE),
    ]
    details = [_make_detail(i.id, i.price, i.category) for i in items]
    inventory, specs_cache = _build_inventory_and_cache(items, details)

    selector = PeripheralSelector()
    with pytest.raises(InventoryError, match="monitor"):
        await selector.select_peripherals("Home", inventory, specs_cache)


# ---------------------------------------------------------------------------
# Gaming monitor ≥144 Hz preference
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gaming_monitor_high_refresh() -> None:
    """Gaming monitor selection prefers ≥144Hz monitors (via spec filter)."""
    monitor_standard = _make_item(10, 500.0, ComponentCategory.MONITOR, sku="MON-60HZ")
    monitor_144hz = _make_item(11, 250.0, ComponentCategory.MONITOR, sku="MON-144HZ")

    items = [
        _make_item(1, 100.0, ComponentCategory.KEYBOARD),
        _make_item(2, 80.0, ComponentCategory.MOUSE),
        monitor_standard,
        monitor_144hz,
        _make_item(3, 150.0, ComponentCategory.SPEAKERS),
    ]
    details = [
        _make_detail(i.id, i.price, i.category)
        for i in items
        if i.category != ComponentCategory.MONITOR
    ] + [
        # Standard 60 Hz monitor — no matching tag
        _make_detail(10, 500.0, ComponentCategory.MONITOR, specs={"refresh_rate": "60hz"}),
        # High-refresh monitor tagged with "144hz"
        _make_detail(11, 250.0, ComponentCategory.MONITOR, specs={"refresh_rate": "144hz"}),
    ]
    inventory, specs_cache = _build_inventory_and_cache(items, details)

    selector = PeripheralSelector()
    selections = await selector.select_peripherals("Gaming", inventory, specs_cache)

    monitor_sel = next(s for s in selections if s.category == PeripheralCategory.MONITOR)
    # The 144 Hz monitor must be selected even though it is cheaper, because
    # it is the only item that passes the gaming tag filter.
    assert monitor_sel.sku == "MON-144HZ"


# ---------------------------------------------------------------------------
# Gaming monitor fallback — no monitors match tag filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gaming_monitor_tag_fallback() -> None:
    """Gaming falls back to all monitors when none match the tag filter."""
    monitor_60hz = _make_item(10, 300.0, ComponentCategory.MONITOR, sku="MON-60HZ")
    monitor_75hz = _make_item(11, 500.0, ComponentCategory.MONITOR, sku="MON-75HZ")

    items = [
        _make_item(1, 100.0, ComponentCategory.KEYBOARD),
        _make_item(2, 80.0, ComponentCategory.MOUSE),
        monitor_60hz,
        monitor_75hz,
        _make_item(3, 150.0, ComponentCategory.SPEAKERS),
    ]
    # Neither monitor has 144hz / high-refresh tags — the fallback path must be used.
    details = [
        _make_detail(i.id, i.price, i.category)
        for i in items
        if i.category != ComponentCategory.MONITOR
    ] + [
        _make_detail(10, 300.0, ComponentCategory.MONITOR, specs={"refresh_rate": "60hz"}),
        _make_detail(11, 500.0, ComponentCategory.MONITOR, specs={"refresh_rate": "75hz"}),
    ]
    inventory, specs_cache = _build_inventory_and_cache(items, details)

    selector = PeripheralSelector()
    selections = await selector.select_peripherals("Gaming", inventory, specs_cache)

    monitor_sel = next(s for s in selections if s.category == PeripheralCategory.MONITOR)
    # With no tag match, all monitors are candidates; premium picks the most expensive.
    assert monitor_sel.sku == "MON-75HZ"
    assert monitor_sel.price == 500.0


# ---------------------------------------------------------------------------
# Single item per category
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_item_category() -> None:
    """Works correctly when only one item is available per category."""
    items = [
        _make_item(1, 25.0, ComponentCategory.KEYBOARD),
        _make_item(2, 18.0, ComponentCategory.MOUSE),
        _make_item(3, 150.0, ComponentCategory.MONITOR),
    ]
    details = [_make_detail(i.id, i.price, i.category) for i in items]
    inventory, specs_cache = _build_inventory_and_cache(items, details)

    selector = PeripheralSelector()
    selections = await selector.select_peripherals("Home", inventory, specs_cache)

    assert len(selections) == 3
    assert all(isinstance(s, PeripheralSelection) for s in selections)
    skus = {s.sku for s in selections}
    assert skus == {"SKU-1", "SKU-2", "SKU-3"}
