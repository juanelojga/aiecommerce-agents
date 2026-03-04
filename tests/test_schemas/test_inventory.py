"""Tests for inventory Pydantic schemas."""

import pytest
from pydantic import ValidationError

from orchestrator.schemas.inventory import (
    ComponentCategory,
    ComponentSelection,
    InventoryItem,
    InventoryResponse,
    ProductSpecs,
    TowerBuild,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

VALID_SPECS_DATA: dict[str, object] = {
    "id": 10,
    "sku": "CPU-001",
}

VALID_ITEM_DATA: dict[str, object] = {
    "id": 1,
    "sku": "CPU-001",
    "name": "Ryzen 9 7950X",
    "category": "cpu",
    "price": 699.99,
    "available_quantity": 5,
    "is_active": True,
}

VALID_SELECTION_DATA: dict[str, object] = {
    "sku": "CPU-001",
    "name": "Ryzen 9 7950X",
    "category": "cpu",
    "price": 699.99,
    "specs": VALID_SPECS_DATA,
}


def _make_selection(
    category: str = "cpu", sku: str = "CPU-001", price: float = 100.0
) -> dict[str, object]:
    """Return a minimal valid ComponentSelection dict for the given category."""
    return {
        "sku": sku,
        "name": f"Component {sku}",
        "category": category,
        "price": price,
        "specs": {"id": 1, "sku": sku},
    }


# ---------------------------------------------------------------------------
# ComponentCategory
# ---------------------------------------------------------------------------


def test_component_category_enum_values() -> None:
    """All eight expected component categories must be present."""
    expected = {"cpu", "motherboard", "ram", "gpu", "ssd", "psu", "case", "fan"}
    actual = {member.value for member in ComponentCategory}
    assert actual == expected


def test_component_category_is_string_enum() -> None:
    """ComponentCategory values should be usable as plain strings."""
    assert ComponentCategory.CPU.value == "cpu"
    assert isinstance(ComponentCategory.GPU, str)


# ---------------------------------------------------------------------------
# InventoryItem
# ---------------------------------------------------------------------------


def test_inventory_item_valid() -> None:
    """Valid data should construct an InventoryItem without errors."""
    item = InventoryItem(**VALID_ITEM_DATA)
    assert item.id == 1
    assert item.sku == "CPU-001"
    assert item.category == ComponentCategory.CPU
    assert item.last_bundled_date is None


def test_inventory_item_with_last_bundled_date() -> None:
    """last_bundled_date is stored when provided."""
    data = {**VALID_ITEM_DATA, "last_bundled_date": "2025-01-15"}
    item = InventoryItem(**data)
    assert item.last_bundled_date == "2025-01-15"


def test_inventory_item_missing_required() -> None:
    """Omitting required fields must raise a ValidationError."""
    incomplete = {k: v for k, v in VALID_ITEM_DATA.items() if k != "sku"}
    with pytest.raises(ValidationError):
        InventoryItem(**incomplete)


def test_inventory_item_invalid_category() -> None:
    """An unknown category string must raise a ValidationError."""
    bad = {**VALID_ITEM_DATA, "category": "unknown_category"}
    with pytest.raises(ValidationError):
        InventoryItem(**bad)


# ---------------------------------------------------------------------------
# ProductSpecs
# ---------------------------------------------------------------------------


def test_product_specs_optional_fields() -> None:
    """Optional fields on ProductSpecs default to None / False / 0."""
    specs = ProductSpecs(id=1, sku="MB-001")
    assert specs.socket is None
    assert specs.ddr_generation is None
    assert specs.form_factor is None
    assert specs.wattage is None
    assert specs.tdp is None
    assert specs.ssd_interface is None
    assert specs.has_integrated_psu is False
    assert specs.included_fans == 0
    assert specs.ram_speed is None
    assert specs.extra_specs == {}


def test_product_specs_all_fields() -> None:
    """All provided fields are stored correctly on ProductSpecs."""
    specs = ProductSpecs(
        id=2,
        sku="RAM-001",
        socket="AM5",
        ddr_generation="DDR5",
        form_factor="DIMM",
        wattage=None,
        tdp=15,
        ssd_interface=None,
        has_integrated_psu=False,
        included_fans=0,
        ram_speed=6000,
        extra_specs={"latency": "CL30"},
    )
    assert specs.ram_speed == 6000
    assert specs.extra_specs == {"latency": "CL30"}


# ---------------------------------------------------------------------------
# InventoryResponse
# ---------------------------------------------------------------------------


def test_inventory_response_valid() -> None:
    """InventoryResponse wraps a count and a list of InventoryItems."""
    payload = {"count": 2, "results": [VALID_ITEM_DATA, {**VALID_ITEM_DATA, "id": 2}]}
    response = InventoryResponse(**payload)
    assert response.count == 2
    assert len(response.results) == 2
    assert all(isinstance(r, InventoryItem) for r in response.results)


def test_inventory_response_empty() -> None:
    """InventoryResponse accepts an empty results list."""
    response = InventoryResponse(count=0, results=[])
    assert response.count == 0
    assert response.results == []


# ---------------------------------------------------------------------------
# ComponentSelection
# ---------------------------------------------------------------------------


def test_component_selection_round_trip() -> None:
    """Serialization then deserialization of ComponentSelection must be lossless."""
    selection = ComponentSelection(**VALID_SELECTION_DATA)
    dumped = selection.model_dump()
    restored = ComponentSelection(**dumped)
    assert restored == selection


def test_component_selection_stores_specs() -> None:
    """ComponentSelection.specs must be a ProductSpecs instance."""
    selection = ComponentSelection(**VALID_SELECTION_DATA)
    assert isinstance(selection.specs, ProductSpecs)
    assert selection.specs.sku == "CPU-001"


# ---------------------------------------------------------------------------
# TowerBuild
# ---------------------------------------------------------------------------


def test_tower_build_hash_default() -> None:
    """bundle_hash defaults to an empty string."""
    build = TowerBuild(
        tier="Home",
        cpu=ComponentSelection(**_make_selection("cpu", "CPU-001", 300.0)),
        motherboard=ComponentSelection(**_make_selection("motherboard", "MB-001", 150.0)),
        ram=ComponentSelection(**_make_selection("ram", "RAM-001", 80.0)),
        ssd=ComponentSelection(**_make_selection("ssd", "SSD-001", 100.0)),
        psu=ComponentSelection(**_make_selection("psu", "PSU-001", 90.0)),
        case=ComponentSelection(**_make_selection("case", "CASE-001", 70.0)),
    )
    assert build.bundle_hash == ""
    assert build.total_price == 0.0
    assert build.gpu is None
    assert build.fans == []


def test_tower_build_with_gpu_and_fans() -> None:
    """TowerBuild accepts optional gpu and a list of fans."""
    build = TowerBuild(
        tier="Gaming",
        cpu=ComponentSelection(**_make_selection("cpu", "CPU-G", 500.0)),
        motherboard=ComponentSelection(**_make_selection("motherboard", "MB-G", 200.0)),
        ram=ComponentSelection(**_make_selection("ram", "RAM-G", 120.0)),
        gpu=ComponentSelection(**_make_selection("gpu", "GPU-G", 800.0)),
        ssd=ComponentSelection(**_make_selection("ssd", "SSD-G", 150.0)),
        psu=ComponentSelection(**_make_selection("psu", "PSU-G", 130.0)),
        case=ComponentSelection(**_make_selection("case", "CASE-G", 100.0)),
        fans=[ComponentSelection(**_make_selection("fan", "FAN-G", 20.0))],
        bundle_hash="abc123",
        total_price=2020.0,
    )
    assert build.gpu is not None
    assert len(build.fans) == 1
    assert build.bundle_hash == "abc123"
    assert build.total_price == 2020.0
