"""Tests for the Inventory Architect LangGraph node (Task 13).

Covers FR-1.1 through FR-1.7:

- Home tier selects cheapest valid configuration.
- Business tier selects mid-range balanced configuration.
- Gaming tier selects performance-focused configuration with GPU.
- Compatibility failures are caught and propagated as errors.
- SHA-256 uniqueness is verified; duplicate builds trigger component swaps.
- PSU is auto-added when the selected case does not include one.
- 2-3 fans are auto-added for Gaming tier when the case lacks them.
- Components with the oldest ``last_bundled_date`` are prioritised.
- Empty inventory returns an error state.
- API errors return a failed state without raising.
- Towers are persisted to the Local Registry after a successful build.
- ComponentAudit records are updated with bundle usage after each build.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.core.exceptions import (
    APIClientError,
    UniquenessError,
)
from orchestrator.graph.nodes.inventory_architect import (
    _build_alternatives,
    _build_component_skus,
    _collect_skus,
    _rotation_sort_key,
    _select_components_for_tier,
    _select_item_for_tier,
    _should_add_fans,
    _should_add_psu,
    inventory_architect_node,
)
from orchestrator.graph.state import GraphState
from orchestrator.schemas.product import (
    ComponentCategory,
    ComponentSelection,
    ProductDetail,
    ProductListItem,
    ProductListResponse,
    TowerBuild,
)
from orchestrator.services.uniqueness import UniquenessEngine

# ---------------------------------------------------------------------------
# Test fixture helpers
# ---------------------------------------------------------------------------

_SOCKET = "AM5"
_MEMORY_TYPE = "DDR5"
_SSD_INTERFACE = "M.2"


def _make_product_detail(
    product_id: int,
    sku: str,
    category: ComponentCategory,
    price: float = 100.0,
    last_bundled_date: str | None = None,
    extra_specs: dict[str, Any] | None = None,
) -> ProductDetail:
    """Build a minimal :class:`ProductDetail` for testing."""
    specs: dict[str, Any] = {}
    # Provide minimal compatible specs by category.
    if category == ComponentCategory.CPU:
        specs = {"socket": _SOCKET, "tdp": 65}
    elif category == ComponentCategory.MOTHERBOARD:
        specs = {
            "socket": _SOCKET,
            "memory_type": _MEMORY_TYPE,
            "supported_ssd_interfaces": [_SSD_INTERFACE],
            "form_factor": "ATX",
        }
    elif category == ComponentCategory.RAM:
        specs = {"memory_type": _MEMORY_TYPE}
    elif category == ComponentCategory.SSD:
        specs = {"interface": _SSD_INTERFACE}
    elif category == ComponentCategory.PSU:
        specs = {"wattage": 750}
    elif category == ComponentCategory.CASE:
        specs = {"form_factor": "ATX"}
    elif category == ComponentCategory.GPU:
        specs = {"tdp": 200}
    elif category == ComponentCategory.FAN:
        specs = {}

    if extra_specs:
        specs.update(extra_specs)

    return ProductDetail(
        id=product_id,
        sku=sku,
        code=sku,
        normalized_name=f"Product {sku}",
        price=price,
        category=category,
        specs=specs,
        total_available_stock=10,
    )


def _make_list_item(
    product_id: int,
    sku: str,
    category: ComponentCategory,
    price: float = 100.0,
    last_bundled_date: str | None = None,
) -> ProductListItem:
    """Build a minimal :class:`ProductListItem` for testing."""
    return ProductListItem(
        id=product_id,
        code=sku,
        sku=sku,
        normalized_name=f"Product {sku}",
        price=price,
        category=category,
        last_bundled_date=last_bundled_date,
        is_active=True,
        total_available_stock=10,
    )


def _make_component_selection(
    sku: str,
    category: ComponentCategory,
    price: float = 100.0,
    spec_overrides: dict[str, Any] | None = None,
    product_id: int = 1,
) -> ComponentSelection:
    """Build a :class:`ComponentSelection` for testing."""
    specs = _make_product_detail(product_id, sku, category, price, extra_specs=spec_overrides)
    return ComponentSelection(
        sku=sku,
        normalized_name=f"Product {sku}",
        category=category,
        price=price,
        specs=specs,
    )


def _make_build(
    tier: str = "Home",
    cpu_sku: str = "CPU-001",
    mb_sku: str = "MB-001",
    ram_sku: str = "RAM-001",
    ssd_sku: str = "SSD-001",
    psu_sku: str = "PSU-001",
    case_sku: str = "CASE-001",
    gpu_sku: str | None = None,
    fans: list[ComponentSelection] | None = None,
) -> TowerBuild:
    """Build a complete :class:`TowerBuild` with compatible specs."""
    return TowerBuild(
        tier=tier,
        cpu=_make_component_selection(cpu_sku, ComponentCategory.CPU),
        motherboard=_make_component_selection(mb_sku, ComponentCategory.MOTHERBOARD),
        ram=_make_component_selection(ram_sku, ComponentCategory.RAM),
        ssd=_make_component_selection(ssd_sku, ComponentCategory.SSD),
        psu=_make_component_selection(psu_sku, ComponentCategory.PSU),
        case=_make_component_selection(case_sku, ComponentCategory.CASE),
        gpu=(_make_component_selection(gpu_sku, ComponentCategory.GPU) if gpu_sku else None),
        fans=fans or [],
        total_price=500.0,
    )


def _build_standard_inventory(
    extra_items: dict[ComponentCategory, list[ProductListItem]] | None = None,
) -> dict[str, list[ProductListItem]]:
    """Return a minimal inventory with one item per required category."""
    items: dict[str, list[ProductListItem]] = {
        ComponentCategory.CPU.value: [
            _make_list_item(1, "CPU-001", ComponentCategory.CPU, price=200.0)
        ],
        ComponentCategory.MOTHERBOARD.value: [
            _make_list_item(2, "MB-001", ComponentCategory.MOTHERBOARD, price=150.0)
        ],
        ComponentCategory.RAM.value: [
            _make_list_item(3, "RAM-001", ComponentCategory.RAM, price=80.0)
        ],
        ComponentCategory.SSD.value: [
            _make_list_item(4, "SSD-001", ComponentCategory.SSD, price=60.0)
        ],
        ComponentCategory.PSU.value: [
            _make_list_item(5, "PSU-001", ComponentCategory.PSU, price=90.0)
        ],
        ComponentCategory.CASE.value: [
            _make_list_item(6, "CASE-001", ComponentCategory.CASE, price=70.0)
        ],
        ComponentCategory.GPU.value: [
            _make_list_item(7, "GPU-001", ComponentCategory.GPU, price=500.0)
        ],
        ComponentCategory.FAN.value: [
            _make_list_item(8, "FAN-001", ComponentCategory.FAN, price=20.0),
            _make_list_item(9, "FAN-002", ComponentCategory.FAN, price=25.0),
        ],
    }
    if extra_items:
        for cat, more_items in extra_items.items():
            items.setdefault(cat.value, []).extend(more_items)
    return items


def _build_standard_specs_cache(
    inventory: dict[str, list[ProductListItem]],
    extra_specs: dict[int, dict[str, Any]] | None = None,
) -> dict[int, ProductDetail]:
    """Build a specs cache from a standard inventory dict."""
    cache: dict[int, ProductDetail] = {}
    for items in inventory.values():
        for item in items:
            cache[item.id] = _make_product_detail(item.id, item.sku, item.category, item.price)
    if extra_specs:
        for pid, spec_overrides in extra_specs.items():
            if pid in cache:
                existing = cache[pid]
                cache[pid] = existing.model_copy(
                    update={"specs": {**existing.specs, **spec_overrides}}
                )
    return cache


# ---------------------------------------------------------------------------
# Helper: build mock API client
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Helper: build mock DB session and repositories
# ---------------------------------------------------------------------------


def _make_session_mock() -> tuple[Any, Any, Any]:
    """Return (mock_session, mock_tower_repo, mock_audit_repo) mocks."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_tower_repo = AsyncMock()
    mock_tower_repo.create = AsyncMock()

    mock_audit_repo = AsyncMock()
    mock_audit_repo.upsert = AsyncMock()
    mock_audit_repo.record_bundle_usage = AsyncMock()

    return mock_session, mock_tower_repo, mock_audit_repo


# ---------------------------------------------------------------------------
# Unit tests: helper functions
# ---------------------------------------------------------------------------


class TestRotationSortKey:
    """Tests for _rotation_sort_key."""

    def test_none_date_returns_lowest_priority_tuple(self) -> None:
        """Items with no last_bundled_date are sorted first (priority 0)."""
        item = _make_list_item(1, "A", ComponentCategory.CPU)
        assert _rotation_sort_key(item) == (0, "")

    def test_older_date_sorts_before_newer(self) -> None:
        """Older ISO-8601 dates produce a lower sort key."""
        old = _make_list_item(1, "A", ComponentCategory.CPU, last_bundled_date="2024-01-01")
        new = _make_list_item(2, "B", ComponentCategory.CPU, last_bundled_date="2025-06-01")
        assert _rotation_sort_key(old) < _rotation_sort_key(new)


class TestSelectItemForTier:
    """Tests for _select_item_for_tier."""

    def test_empty_list_returns_none(self) -> None:
        """Empty inventory returns None for all tiers."""
        assert _select_item_for_tier([], "Home") is None

    def test_home_selects_cheapest(self) -> None:
        """Home tier picks the item with the lowest price."""
        items = [
            _make_list_item(1, "A", ComponentCategory.CPU, price=500.0),
            _make_list_item(2, "B", ComponentCategory.CPU, price=100.0),
            _make_list_item(3, "C", ComponentCategory.CPU, price=300.0),
        ]
        result = _select_item_for_tier(items, "Home")
        assert result is not None
        assert result.sku == "B"

    def test_gaming_selects_most_expensive(self) -> None:
        """Gaming tier picks the item with the highest price."""
        items = [
            _make_list_item(1, "A", ComponentCategory.CPU, price=100.0),
            _make_list_item(2, "B", ComponentCategory.CPU, price=800.0),
            _make_list_item(3, "C", ComponentCategory.CPU, price=400.0),
        ]
        result = _select_item_for_tier(items, "Gaming")
        assert result is not None
        assert result.sku == "B"

    def test_business_selects_middle(self) -> None:
        """Business tier picks the middle-priced item."""
        items = [
            _make_list_item(1, "A", ComponentCategory.CPU, price=100.0),
            _make_list_item(2, "B", ComponentCategory.CPU, price=300.0),
            _make_list_item(3, "C", ComponentCategory.CPU, price=500.0),
        ]
        result = _select_item_for_tier(items, "Business")
        # Middle index = 1 → "B" (300.0)
        assert result is not None
        assert result.sku == "B"

    def test_rotation_priority_overrides_price(self) -> None:
        """Never-bundled item is selected even if not the cheapest."""
        items = [
            _make_list_item(
                1, "CHEAP", ComponentCategory.CPU, price=50.0, last_bundled_date="2025-01-01"
            ),
            _make_list_item(2, "OLD", ComponentCategory.CPU, price=150.0, last_bundled_date=None),
        ]
        # Home tier: rotation key takes priority; never-bundled "OLD" wins.
        result = _select_item_for_tier(items, "Home")
        assert result is not None
        assert result.sku == "OLD"


class TestShouldAddPsu:
    """Tests for _should_add_psu."""

    def test_no_includes_psu_spec_requires_psu(self) -> None:
        """Case without includes_psu spec needs a standalone PSU."""
        detail = _make_product_detail(1, "CASE-1", ComponentCategory.CASE)
        assert _should_add_psu(detail) is True

    def test_includes_psu_false_requires_psu(self) -> None:
        """Case with includes_psu=False needs a standalone PSU."""
        detail = _make_product_detail(
            1, "CASE-1", ComponentCategory.CASE, extra_specs={"includes_psu": False}
        )
        assert _should_add_psu(detail) is True

    def test_includes_psu_true_does_not_require_psu(self) -> None:
        """Case with includes_psu=True already has an integrated PSU."""
        detail = _make_product_detail(
            1, "CASE-1", ComponentCategory.CASE, extra_specs={"includes_psu": True}
        )
        assert _should_add_psu(detail) is False


class TestShouldAddFans:
    """Tests for _should_add_fans."""

    def test_gaming_without_fans_requires_fans(self) -> None:
        """Gaming tier case without fans spec requires fan auto-add."""
        detail = _make_product_detail(1, "CASE-1", ComponentCategory.CASE)
        assert _should_add_fans("Gaming", detail) is True

    def test_gaming_with_includes_fans_no_auto_add(self) -> None:
        """Gaming tier case that already includes fans does not need auto-add."""
        detail = _make_product_detail(
            1, "CASE-1", ComponentCategory.CASE, extra_specs={"includes_fans": True}
        )
        assert _should_add_fans("Gaming", detail) is False

    def test_home_tier_never_adds_fans(self) -> None:
        """Home tier never triggers fan auto-add regardless of case specs."""
        detail = _make_product_detail(1, "CASE-1", ComponentCategory.CASE)
        assert _should_add_fans("Home", detail) is False

    def test_business_tier_never_adds_fans(self) -> None:
        """Business tier never triggers fan auto-add."""
        detail = _make_product_detail(1, "CASE-1", ComponentCategory.CASE)
        assert _should_add_fans("Business", detail) is False


class TestBuildAlternatives:
    """Tests for _build_alternatives."""

    def test_excludes_primary_selections(self) -> None:
        """Alternative lists must not include the already-selected SKU."""
        build = _make_build()
        inventory: dict[str, list[ProductListItem]] = {
            ComponentCategory.SSD.value: [
                _make_list_item(4, "SSD-001", ComponentCategory.SSD),
                _make_list_item(10, "SSD-002", ComponentCategory.SSD),
            ],
            ComponentCategory.RAM.value: [
                _make_list_item(3, "RAM-001", ComponentCategory.RAM),
            ],
            ComponentCategory.PSU.value: [
                _make_list_item(5, "PSU-001", ComponentCategory.PSU),
                _make_list_item(11, "PSU-002", ComponentCategory.PSU),
            ],
        }
        cache = _build_standard_specs_cache(inventory)
        alts = _build_alternatives(inventory, cache, build)

        assert "SSD-001" not in [s.sku for s in alts.get("ssd", [])]
        assert "PSU-001" not in [s.sku for s in alts.get("psu", [])]
        # RAM has only one item (primary), so no alternatives.
        assert "ram" not in alts

    def test_returns_alternative_ssds_and_psus(self) -> None:
        """Correct alternative SKUs are present in the returned dict."""
        build = _make_build()
        inventory: dict[str, list[ProductListItem]] = {
            ComponentCategory.SSD.value: [
                _make_list_item(4, "SSD-001", ComponentCategory.SSD),
                _make_list_item(10, "SSD-002", ComponentCategory.SSD),
            ],
            ComponentCategory.RAM.value: [
                _make_list_item(3, "RAM-001", ComponentCategory.RAM),
                _make_list_item(12, "RAM-002", ComponentCategory.RAM),
            ],
            ComponentCategory.PSU.value: [
                _make_list_item(5, "PSU-001", ComponentCategory.PSU),
                _make_list_item(11, "PSU-002", ComponentCategory.PSU),
            ],
        }
        cache = _build_standard_specs_cache(inventory)
        alts = _build_alternatives(inventory, cache, build)

        assert any(s.sku == "SSD-002" for s in alts.get("ssd", []))
        assert any(s.sku == "RAM-002" for s in alts.get("ram", []))
        assert any(s.sku == "PSU-002" for s in alts.get("psu", []))


class TestBuildComponentSkus:
    """Tests for _build_component_skus."""

    def test_core_skus_present(self) -> None:
        """Core component SKUs are all present in the output dict."""
        build = _make_build()
        skus = _build_component_skus(build)
        assert skus["cpu"] == "CPU-001"
        assert skus["motherboard"] == "MB-001"
        assert skus["ram"] == "RAM-001"
        assert skus["ssd"] == "SSD-001"
        assert skus["psu"] == "PSU-001"
        assert skus["case"] == "CASE-001"

    def test_gpu_included_when_present(self) -> None:
        """GPU SKU is included when the build has a GPU."""
        build = _make_build(gpu_sku="GPU-001")
        skus = _build_component_skus(build)
        assert skus["gpu"] == "GPU-001"

    def test_gpu_absent_when_none(self) -> None:
        """GPU key is absent when the build has no GPU."""
        build = _make_build()
        skus = _build_component_skus(build)
        assert "gpu" not in skus

    def test_fans_list_included_when_present(self) -> None:
        """Fan SKUs are included as a list when fans are present."""
        fan = _make_component_selection("FAN-001", ComponentCategory.FAN, product_id=8)
        build = _make_build(fans=[fan])
        skus = _build_component_skus(build)
        assert skus["fans"] == ["FAN-001"]


class TestCollectSkus:
    """Tests for _collect_skus."""

    def test_returns_all_core_skus(self) -> None:
        """All six core SKUs are returned for a build without GPU/fans."""
        build = _make_build()
        skus = _collect_skus(build)
        assert set(skus) == {"CPU-001", "MB-001", "RAM-001", "SSD-001", "PSU-001", "CASE-001"}

    def test_includes_gpu_sku(self) -> None:
        """GPU SKU is included when present."""
        build = _make_build(gpu_sku="GPU-001")
        skus = _collect_skus(build)
        assert "GPU-001" in skus

    def test_includes_fan_skus(self) -> None:
        """Fan SKUs are included when fans are present."""
        fan = _make_component_selection("FAN-001", ComponentCategory.FAN, product_id=8)
        build = _make_build(fans=[fan])
        skus = _collect_skus(build)
        assert "FAN-001" in skus


# ---------------------------------------------------------------------------
# Unit tests: _select_components_for_tier
# ---------------------------------------------------------------------------


class TestSelectComponentsForTier:
    """Tests for _select_components_for_tier."""

    @pytest.mark.asyncio
    async def test_home_tier_selects_cheapest(self) -> None:
        """Home tier selects the cheapest valid component in each category."""
        # Provide two CPUs; Home should pick the cheaper one.
        inventory = _build_standard_inventory(
            extra_items={
                ComponentCategory.CPU: [
                    _make_list_item(20, "CPU-CHEAP", ComponentCategory.CPU, price=50.0),
                ]
            }
        )
        # Give CPU-001 price=200 and CPU-CHEAP price=50 so cheapest = CPU-CHEAP.
        inventory[ComponentCategory.CPU.value] = [
            _make_list_item(1, "CPU-001", ComponentCategory.CPU, price=200.0),
            _make_list_item(20, "CPU-CHEAP", ComponentCategory.CPU, price=50.0),
        ]
        cache = _build_standard_specs_cache(inventory)

        audit_repo = AsyncMock()
        build = await _select_components_for_tier("Home", inventory, cache, audit_repo)

        assert build.tier == "Home"
        assert build.cpu.sku == "CPU-CHEAP"

    @pytest.mark.asyncio
    async def test_gaming_tier_selects_most_expensive(self) -> None:
        """Gaming tier selects the highest-priced component in each category."""
        inventory = _build_standard_inventory()
        inventory[ComponentCategory.CPU.value] = [
            _make_list_item(1, "CPU-BUDGET", ComponentCategory.CPU, price=100.0),
            _make_list_item(20, "CPU-POWER", ComponentCategory.CPU, price=800.0),
        ]
        cache = _build_standard_specs_cache(inventory)

        audit_repo = AsyncMock()
        build = await _select_components_for_tier("Gaming", inventory, cache, audit_repo)

        assert build.tier == "Gaming"
        assert build.cpu.sku == "CPU-POWER"
        # Gaming tier requires a GPU.
        assert build.gpu is not None

    @pytest.mark.asyncio
    async def test_business_tier_selects_balanced(self) -> None:
        """Business tier selects a mid-range component when options are available."""
        inventory = _build_standard_inventory()
        inventory[ComponentCategory.CPU.value] = [
            _make_list_item(1, "CPU-LOW", ComponentCategory.CPU, price=100.0),
            _make_list_item(20, "CPU-MID", ComponentCategory.CPU, price=300.0),
            _make_list_item(21, "CPU-HIGH", ComponentCategory.CPU, price=600.0),
        ]
        cache = _build_standard_specs_cache(inventory)

        audit_repo = AsyncMock()
        build = await _select_components_for_tier("Business", inventory, cache, audit_repo)

        assert build.tier == "Business"
        # Middle index of [100, 300, 600] sorted ascending = 300 (index 1).
        assert build.cpu.sku == "CPU-MID"

    @pytest.mark.asyncio
    async def test_gaming_has_no_gpu_raises_inventory_error(self) -> None:
        """Gaming tier raises InventoryError when no GPU is available."""
        from orchestrator.core.exceptions import InventoryError

        inventory = _build_standard_inventory()
        inventory[ComponentCategory.GPU.value] = []  # Empty GPU inventory.
        cache = _build_standard_specs_cache(inventory)

        audit_repo = AsyncMock()
        with pytest.raises(InventoryError, match="GPU"):
            await _select_components_for_tier("Gaming", inventory, cache, audit_repo)

    @pytest.mark.asyncio
    async def test_missing_required_category_raises_inventory_error(self) -> None:
        """InventoryError is raised when a required category has no items."""
        from orchestrator.core.exceptions import InventoryError

        inventory = _build_standard_inventory()
        inventory[ComponentCategory.CPU.value] = []  # Remove all CPUs.
        cache = _build_standard_specs_cache(inventory)

        audit_repo = AsyncMock()
        with pytest.raises(InventoryError, match="cpu"):
            await _select_components_for_tier("Home", inventory, cache, audit_repo)

    @pytest.mark.asyncio
    async def test_gaming_auto_adds_fans(self) -> None:
        """Gaming tier auto-adds fans when the case does not include them."""
        inventory = _build_standard_inventory()
        # Ensure case has no includes_fans spec.
        case_id = inventory[ComponentCategory.CASE.value][0].id
        cache = _build_standard_specs_cache(inventory)
        # Remove includes_fans from case specs (already absent by default).
        assert not cache[case_id].specs.get("includes_fans")

        audit_repo = AsyncMock()
        build = await _select_components_for_tier("Gaming", inventory, cache, audit_repo)

        assert len(build.fans) > 0

    @pytest.mark.asyncio
    async def test_auto_adds_psu_when_case_lacks_one(self) -> None:
        """PSU is selected from inventory when the case does not include one."""
        inventory = _build_standard_inventory()
        cache = _build_standard_specs_cache(inventory)

        audit_repo = AsyncMock()
        build = await _select_components_for_tier("Home", inventory, cache, audit_repo)

        # Case has no includes_psu, so a standalone PSU must be in the build.
        assert build.psu is not None
        assert build.psu.sku == "PSU-001"

    @pytest.mark.asyncio
    async def test_prioritizes_rotation_never_bundled_first(self) -> None:
        """Components with no last_bundled_date are prioritised (oldest = None)."""
        inventory = _build_standard_inventory()
        inventory[ComponentCategory.CPU.value] = [
            _make_list_item(
                1, "CPU-OLD", ComponentCategory.CPU, price=200.0, last_bundled_date="2024-01-01"
            ),
            _make_list_item(
                20, "CPU-NEVER", ComponentCategory.CPU, price=300.0, last_bundled_date=None
            ),
        ]
        cache = _build_standard_specs_cache(inventory)

        audit_repo = AsyncMock()
        build = await _select_components_for_tier("Home", inventory, cache, audit_repo)

        # CPU-NEVER has no last_bundled_date (priority = 0) so it is selected first,
        # even though it is more expensive.
        assert build.cpu.sku == "CPU-NEVER"


# ---------------------------------------------------------------------------
# Integration tests: inventory_architect_node
# ---------------------------------------------------------------------------


def _build_node_mocks(
    inventory: dict[str, list[ProductListItem]] | None = None,
    specs_cache: dict[int, ProductDetail] | None = None,
    hash_exists: bool = False,
) -> tuple[Any, Any, Any]:
    """Build all mocks needed to test the node end-to-end.

    Returns:
        Tuple of (mock_api_client, mock_tower_repo, mock_audit_repo).
    """
    if inventory is None:
        inventory = _build_standard_inventory()
    if specs_cache is None:
        specs_cache = _build_standard_specs_cache(inventory)

    mock_api = _make_api_client_mock(inventory, specs_cache)
    _, mock_tower_repo, mock_audit_repo = _make_session_mock()
    mock_tower_repo.hash_exists = AsyncMock(return_value=hash_exists)

    return mock_api, mock_tower_repo, mock_audit_repo


@pytest.mark.asyncio
async def test_inventory_architect_home_tier() -> None:
    """Node selects cheapest valid components for Home tier."""
    inventory = _build_standard_inventory()
    inventory[ComponentCategory.CPU.value] = [
        _make_list_item(1, "CPU-BUDGET", ComponentCategory.CPU, price=100.0),
        _make_list_item(20, "CPU-HIGH", ComponentCategory.CPU, price=600.0),
    ]
    cache = _build_standard_specs_cache(inventory)
    mock_api, mock_tower_repo, mock_audit_repo = _build_node_mocks(inventory, cache)

    state = GraphState(requested_tiers=["Home"])

    with (
        patch(
            "orchestrator.graph.nodes.inventory_architect.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.TowerRepository",
            return_value=mock_tower_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.UniquenessEngine",
            return_value=_make_uniqueness_engine(mock_tower_repo),
        ),
        patch("orchestrator.graph.nodes.inventory_architect.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await inventory_architect_node(state)

    assert result["run_status"] == "completed"
    assert len(result["completed_builds"]) == 1  # type: ignore[arg-type]
    build_dict = result["completed_builds"][0]  # type: ignore[index]
    assert build_dict["tier"] == "Home"
    assert build_dict["cpu"]["sku"] == "CPU-BUDGET"


@pytest.mark.asyncio
async def test_inventory_architect_gaming_tier() -> None:
    """Node selects high-end components and includes a GPU for Gaming tier."""
    inventory = _build_standard_inventory()
    inventory[ComponentCategory.CPU.value] = [
        _make_list_item(1, "CPU-LOW", ComponentCategory.CPU, price=100.0),
        _make_list_item(20, "CPU-HIGH", ComponentCategory.CPU, price=700.0),
    ]
    cache = _build_standard_specs_cache(inventory)
    mock_api, mock_tower_repo, mock_audit_repo = _build_node_mocks(inventory, cache)

    state = GraphState(requested_tiers=["Gaming"])

    with (
        patch(
            "orchestrator.graph.nodes.inventory_architect.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.TowerRepository",
            return_value=mock_tower_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.UniquenessEngine",
            return_value=_make_uniqueness_engine(mock_tower_repo),
        ),
        patch("orchestrator.graph.nodes.inventory_architect.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await inventory_architect_node(state)

    assert result["run_status"] == "completed"
    assert len(result["completed_builds"]) == 1  # type: ignore[arg-type]
    build_dict = result["completed_builds"][0]  # type: ignore[index]
    assert build_dict["tier"] == "Gaming"
    assert build_dict["cpu"]["sku"] == "CPU-HIGH"
    assert build_dict["gpu"] is not None
    assert len(build_dict["fans"]) > 0  # Fans auto-added for Gaming.


@pytest.mark.asyncio
async def test_inventory_architect_business_tier() -> None:
    """Node selects balanced components for Business tier."""
    inventory = _build_standard_inventory()
    inventory[ComponentCategory.CPU.value] = [
        _make_list_item(1, "CPU-LOW", ComponentCategory.CPU, price=100.0),
        _make_list_item(20, "CPU-MID", ComponentCategory.CPU, price=300.0),
        _make_list_item(21, "CPU-HIGH", ComponentCategory.CPU, price=600.0),
    ]
    cache = _build_standard_specs_cache(inventory)
    mock_api, mock_tower_repo, mock_audit_repo = _build_node_mocks(inventory, cache)

    state = GraphState(requested_tiers=["Business"])

    with (
        patch(
            "orchestrator.graph.nodes.inventory_architect.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.TowerRepository",
            return_value=mock_tower_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.UniquenessEngine",
            return_value=_make_uniqueness_engine(mock_tower_repo),
        ),
        patch("orchestrator.graph.nodes.inventory_architect.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await inventory_architect_node(state)

    assert result["run_status"] == "completed"
    build_dict = result["completed_builds"][0]  # type: ignore[index]
    assert build_dict["tier"] == "Business"
    assert build_dict["cpu"]["sku"] == "CPU-MID"


@pytest.mark.asyncio
async def test_inventory_architect_validates_compatibility() -> None:
    """Node records error for tiers where compatibility validation fails."""
    inventory = _build_standard_inventory()
    cache = _build_standard_specs_cache(inventory)
    # Make the motherboard specs use a different socket than the CPU to trigger failure.
    mb_id = inventory[ComponentCategory.MOTHERBOARD.value][0].id
    cache[mb_id] = cache[mb_id].model_copy(
        update={"specs": {**cache[mb_id].specs, "socket": "AM4"}}
    )

    mock_api, mock_tower_repo, mock_audit_repo = _build_node_mocks(inventory, cache)
    state = GraphState(requested_tiers=["Home"])

    with (
        patch(
            "orchestrator.graph.nodes.inventory_architect.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.TowerRepository",
            return_value=mock_tower_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.UniquenessEngine",
            return_value=_make_uniqueness_engine(mock_tower_repo),
        ),
        patch("orchestrator.graph.nodes.inventory_architect.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await inventory_architect_node(state)

    assert result["run_status"] == "failed"
    assert len(result["errors"]) > 0  # type: ignore[arg-type]
    errors: list[str] = result["errors"]  # type: ignore[assignment]
    assert any("socket" in e.lower() for e in errors)


@pytest.mark.asyncio
async def test_inventory_architect_ensures_uniqueness() -> None:
    """Node produces a build with a non-empty bundle_hash (unique build)."""
    inventory = _build_standard_inventory()
    cache = _build_standard_specs_cache(inventory)
    mock_api, mock_tower_repo, mock_audit_repo = _build_node_mocks(inventory, cache)

    state = GraphState(requested_tiers=["Home"])

    with (
        patch(
            "orchestrator.graph.nodes.inventory_architect.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.TowerRepository",
            return_value=mock_tower_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.UniquenessEngine",
            return_value=_make_uniqueness_engine(mock_tower_repo),
        ),
        patch("orchestrator.graph.nodes.inventory_architect.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await inventory_architect_node(state)

    assert result["run_status"] == "completed"
    build_dict = result["completed_builds"][0]  # type: ignore[index]
    assert build_dict["bundle_hash"] != ""


@pytest.mark.asyncio
async def test_inventory_architect_uniqueness_collision_triggers_error() -> None:
    """UniquenessError is recorded when all alternatives are exhausted."""
    inventory = _build_standard_inventory()
    cache = _build_standard_specs_cache(inventory)
    mock_api, mock_tower_repo, mock_audit_repo = _build_node_mocks(
        inventory, cache, hash_exists=True
    )

    # Uniqueness engine that always raises.
    mock_ue = AsyncMock()
    mock_ue.ensure_unique = AsyncMock(
        side_effect=UniquenessError("Could not produce a unique build.")
    )

    state = GraphState(requested_tiers=["Home"])

    with (
        patch(
            "orchestrator.graph.nodes.inventory_architect.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.TowerRepository",
            return_value=mock_tower_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.UniquenessEngine",
            return_value=mock_ue,
        ),
        patch("orchestrator.graph.nodes.inventory_architect.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await inventory_architect_node(state)

    assert result["run_status"] == "failed"
    assert len(result["errors"]) == 1  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_inventory_architect_auto_adds_psu() -> None:
    """Node adds PSU from inventory when the selected case does not include one."""
    inventory = _build_standard_inventory()
    cache = _build_standard_specs_cache(inventory)
    # Ensure case has no includes_psu (default).
    case_id = inventory[ComponentCategory.CASE.value][0].id
    assert not cache[case_id].specs.get("includes_psu")

    mock_api, mock_tower_repo, mock_audit_repo = _build_node_mocks(inventory, cache)
    state = GraphState(requested_tiers=["Home"])

    with (
        patch(
            "orchestrator.graph.nodes.inventory_architect.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.TowerRepository",
            return_value=mock_tower_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.UniquenessEngine",
            return_value=_make_uniqueness_engine(mock_tower_repo),
        ),
        patch("orchestrator.graph.nodes.inventory_architect.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await inventory_architect_node(state)

    assert result["run_status"] == "completed"
    build_dict = result["completed_builds"][0]  # type: ignore[index]
    assert build_dict["psu"] is not None
    assert build_dict["psu"]["sku"] == "PSU-001"


@pytest.mark.asyncio
async def test_inventory_architect_auto_adds_fans() -> None:
    """Node adds fans to Gaming builds when the case does not include them."""
    inventory = _build_standard_inventory()
    cache = _build_standard_specs_cache(inventory)
    mock_api, mock_tower_repo, mock_audit_repo = _build_node_mocks(inventory, cache)

    state = GraphState(requested_tiers=["Gaming"])

    with (
        patch(
            "orchestrator.graph.nodes.inventory_architect.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.TowerRepository",
            return_value=mock_tower_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.UniquenessEngine",
            return_value=_make_uniqueness_engine(mock_tower_repo),
        ),
        patch("orchestrator.graph.nodes.inventory_architect.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await inventory_architect_node(state)

    assert result["run_status"] == "completed"
    build_dict = result["completed_builds"][0]  # type: ignore[index]
    assert len(build_dict["fans"]) >= 1


@pytest.mark.asyncio
async def test_inventory_architect_prioritizes_rotation() -> None:
    """Never-bundled components are selected first (FR-1.7)."""
    inventory = _build_standard_inventory()
    # Provide two CPUs: one never bundled, one recently bundled.
    inventory[ComponentCategory.CPU.value] = [
        _make_list_item(
            1, "CPU-RECENT", ComponentCategory.CPU, price=100.0, last_bundled_date="2025-06-01"
        ),
        _make_list_item(
            20, "CPU-NEVER", ComponentCategory.CPU, price=200.0, last_bundled_date=None
        ),
    ]
    cache = _build_standard_specs_cache(inventory)
    mock_api, mock_tower_repo, mock_audit_repo = _build_node_mocks(inventory, cache)

    state = GraphState(requested_tiers=["Home"])

    with (
        patch(
            "orchestrator.graph.nodes.inventory_architect.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.TowerRepository",
            return_value=mock_tower_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.UniquenessEngine",
            return_value=_make_uniqueness_engine(mock_tower_repo),
        ),
        patch("orchestrator.graph.nodes.inventory_architect.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await inventory_architect_node(state)

    assert result["run_status"] == "completed"
    build_dict = result["completed_builds"][0]  # type: ignore[index]
    assert build_dict["cpu"]["sku"] == "CPU-NEVER"


@pytest.mark.asyncio
async def test_inventory_architect_empty_inventory() -> None:
    """Node returns failed state when a required category has no items."""
    inventory = _build_standard_inventory()
    inventory[ComponentCategory.CPU.value] = []  # Empty CPU inventory.
    cache = _build_standard_specs_cache(inventory)
    mock_api, mock_tower_repo, mock_audit_repo = _build_node_mocks(inventory, cache)

    state = GraphState(requested_tiers=["Home"])

    with (
        patch(
            "orchestrator.graph.nodes.inventory_architect.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.TowerRepository",
            return_value=mock_tower_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.UniquenessEngine",
            return_value=_make_uniqueness_engine(mock_tower_repo),
        ),
        patch("orchestrator.graph.nodes.inventory_architect.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await inventory_architect_node(state)

    assert result["run_status"] == "failed"
    assert len(result["errors"]) > 0  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_inventory_architect_api_error() -> None:
    """Node returns failed state immediately when the API raises an error."""
    mock_api = MagicMock()
    mock_api.list_products = AsyncMock(side_effect=APIClientError("Connection refused"))

    state = GraphState(requested_tiers=["Home"])

    with (
        patch(
            "orchestrator.graph.nodes.inventory_architect.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch("orchestrator.graph.nodes.inventory_architect.async_session_factory"),
    ):
        result = await inventory_architect_node(state)

    assert result["run_status"] == "failed"
    assert len(result["errors"]) > 0  # type: ignore[arg-type]
    assert result["completed_builds"] == []


@pytest.mark.asyncio
async def test_inventory_architect_persists_tower() -> None:
    """Node calls TowerRepository.create once per successful build."""
    inventory = _build_standard_inventory()
    cache = _build_standard_specs_cache(inventory)
    mock_api, mock_tower_repo, mock_audit_repo = _build_node_mocks(inventory, cache)

    state = GraphState(requested_tiers=["Home"])

    with (
        patch(
            "orchestrator.graph.nodes.inventory_architect.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.TowerRepository",
            return_value=mock_tower_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.UniquenessEngine",
            return_value=_make_uniqueness_engine(mock_tower_repo),
        ),
        patch("orchestrator.graph.nodes.inventory_architect.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await inventory_architect_node(state)

    assert result["run_status"] == "completed"
    mock_tower_repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_inventory_architect_records_audit() -> None:
    """Node calls ComponentAuditRepository.record_bundle_usage after each build."""
    inventory = _build_standard_inventory()
    cache = _build_standard_specs_cache(inventory)
    mock_api, mock_tower_repo, mock_audit_repo = _build_node_mocks(inventory, cache)

    state = GraphState(requested_tiers=["Home"])

    with (
        patch(
            "orchestrator.graph.nodes.inventory_architect.AIEcommerceClient",
            return_value=mock_api,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.TowerRepository",
            return_value=mock_tower_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.ComponentAuditRepository",
            return_value=mock_audit_repo,
        ),
        patch(
            "orchestrator.graph.nodes.inventory_architect.UniquenessEngine",
            return_value=_make_uniqueness_engine(mock_tower_repo),
        ),
        patch("orchestrator.graph.nodes.inventory_architect.async_session_factory") as mock_factory,
    ):
        _configure_session_factory(mock_factory)
        result = await inventory_architect_node(state)

    assert result["run_status"] == "completed"
    mock_audit_repo.record_bundle_usage.assert_called_once()


@pytest.mark.asyncio
async def test_inventory_architect_no_tiers_returns_completed() -> None:
    """Node returns completed status with empty builds when no tiers requested."""
    state = GraphState(requested_tiers=[])
    result = await inventory_architect_node(state)

    assert result["run_status"] == "completed"
    assert result["completed_builds"] == []
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# Private helpers used across integration tests
# ---------------------------------------------------------------------------


def _make_uniqueness_engine(mock_tower_repo: Any) -> Any:
    """Return a real UniquenessEngine backed by a mock repo (hash_exists=False)."""
    mock_tower_repo.hash_exists = AsyncMock(return_value=False)
    return UniquenessEngine(tower_repository=mock_tower_repo)


def _configure_session_factory(mock_factory: Any) -> None:
    """Configure the async_session_factory mock as an async context manager."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
