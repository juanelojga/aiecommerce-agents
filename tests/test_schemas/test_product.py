"""Tests for product Pydantic schemas."""

import pytest
from pydantic import ValidationError

from orchestrator.schemas.product import (
    ComponentCategory,
    ComponentSelection,
    ProductDetail,
    ProductListItem,
    ProductListResponse,
    TowerBuild,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

VALID_DETAIL_DATA: dict[str, object] = {
    "id": 10,
    "code": "PROD-001",
    "sku": "CPU-001",
    "normalized_name": "Ryzen 9 7950X",
    "price": 699.99,
    "category": "cpu",
    "specs": {"socket": "AM5", "tdp": 170},
}

VALID_ITEM_DATA: dict[str, object] = {
    "id": 1,
    "code": "PROD-001",
    "sku": "CPU-001",
    "normalized_name": "Ryzen 9 7950X",
    "category": "cpu",
    "price": 699.99,
    "is_active": True,
    "total_available_stock": 5,
}

VALID_SELECTION_DATA: dict[str, object] = {
    "sku": "CPU-001",
    "normalized_name": "Ryzen 9 7950X",
    "category": "cpu",
    "price": 699.99,
    "specs": VALID_DETAIL_DATA,
}


def _make_selection(
    category: str = "cpu", sku: str = "CPU-001", price: float = 100.0
) -> dict[str, object]:
    """Return a minimal valid ComponentSelection dict for the given category."""
    return {
        "sku": sku,
        "normalized_name": f"Component {sku}",
        "category": category,
        "price": price,
        "specs": {
            "id": 1,
            "code": f"PROD-{sku}",
            "sku": sku,
            "normalized_name": f"Component {sku}",
            "price": price,
            "category": category,
        },
    }


# ---------------------------------------------------------------------------
# ComponentCategory
# ---------------------------------------------------------------------------


def test_component_category_enum_values() -> None:
    """All twelve expected component categories must be present."""
    expected = {
        "cpu",
        "motherboard",
        "ram",
        "gpu",
        "ssd",
        "psu",
        "case",
        "fan",
        "keyboard",
        "mouse",
        "monitor",
        "speakers",
    }
    actual = {member.value for member in ComponentCategory}
    assert actual == expected


def test_component_category_is_string_enum() -> None:
    """ComponentCategory values should be usable as plain strings."""
    assert ComponentCategory.CPU.value == "cpu"
    assert isinstance(ComponentCategory.GPU, str)


# ---------------------------------------------------------------------------
# ProductListItem
# ---------------------------------------------------------------------------


def test_product_list_item_valid() -> None:
    """Valid data should construct a ProductListItem without errors."""
    item = ProductListItem(**VALID_ITEM_DATA)
    assert item.id == 1
    assert item.sku == "CPU-001"
    assert item.code == "PROD-001"
    assert item.normalized_name == "Ryzen 9 7950X"
    assert item.category == ComponentCategory.CPU
    assert item.total_available_stock == 5
    assert item.last_bundled_date is None


def test_product_list_item_with_last_bundled_date() -> None:
    """last_bundled_date is stored when provided."""
    data = {**VALID_ITEM_DATA, "last_bundled_date": "2025-01-15"}
    item = ProductListItem(**data)
    assert item.last_bundled_date == "2025-01-15"


def test_product_list_item_missing_required() -> None:
    """Omitting required fields must raise a ValidationError."""
    incomplete = {k: v for k, v in VALID_ITEM_DATA.items() if k != "sku"}
    with pytest.raises(ValidationError):
        ProductListItem(**incomplete)


def test_product_list_item_invalid_category() -> None:
    """An unknown category string must raise a ValidationError."""
    bad = {**VALID_ITEM_DATA, "category": "unknown_category"}
    with pytest.raises(ValidationError):
        ProductListItem(**bad)


# ---------------------------------------------------------------------------
# ProductDetail
# ---------------------------------------------------------------------------


def test_product_detail_optional_fields() -> None:
    """Optional fields on ProductDetail default to None / empty / 0."""
    detail = ProductDetail(
        id=1,
        code="PROD-001",
        sku="MB-001",
        normalized_name="ASUS ROG",
        price=299.99,
        category="motherboard",
    )
    assert detail.model_name is None
    assert detail.description is None
    assert detail.seo_title is None
    assert detail.seo_description is None
    assert detail.gtin is None
    assert detail.specs == {}
    assert detail.image_url is None
    assert detail.image_urls == []
    assert detail.total_available_stock == 0


def test_product_detail_all_fields() -> None:
    """All provided fields are stored correctly on ProductDetail."""
    detail = ProductDetail(
        id=2,
        code="PROD-RAM",
        sku="RAM-001",
        normalized_name="Corsair Vengeance DDR5",
        model_name="CMK32GX5M2B5600C36",
        description="High-performance DDR5 memory.",
        seo_title="Corsair DDR5 RAM",
        seo_description="Buy Corsair DDR5 memory at the best price.",
        price=129.99,
        category="ram",
        gtin="0840006618522",
        specs={"ddr_generation": "DDR5", "ram_speed": 6000, "latency": "CL30"},
        image_url="https://example.com/ram.jpg",
        image_urls=[{"url": "https://example.com/ram.jpg", "alt": "RAM front"}],
        total_available_stock=25,
    )
    assert detail.normalized_name == "Corsair Vengeance DDR5"
    assert detail.specs == {"ddr_generation": "DDR5", "ram_speed": 6000, "latency": "CL30"}
    assert detail.total_available_stock == 25
    assert len(detail.image_urls) == 1


# ---------------------------------------------------------------------------
# ProductListResponse
# ---------------------------------------------------------------------------


def test_product_list_response_valid() -> None:
    """ProductListResponse wraps a count and a list of ProductListItems."""
    payload = {"count": 2, "results": [VALID_ITEM_DATA, {**VALID_ITEM_DATA, "id": 2}]}
    response = ProductListResponse(**payload)
    assert response.count == 2
    assert len(response.results) == 2
    assert all(isinstance(r, ProductListItem) for r in response.results)


def test_product_list_response_empty() -> None:
    """ProductListResponse accepts an empty results list."""
    response = ProductListResponse(count=0, results=[])
    assert response.count == 0
    assert response.results == []


def test_product_list_response_pagination_fields() -> None:
    """ProductListResponse stores next and previous pagination URLs."""
    payload = {
        "count": 50,
        "next": "https://api.example.com/api/v1/products/?page=3",
        "previous": "https://api.example.com/api/v1/products/?page=1",
        "results": [VALID_ITEM_DATA],
    }
    response = ProductListResponse(**payload)
    assert response.next == "https://api.example.com/api/v1/products/?page=3"
    assert response.previous == "https://api.example.com/api/v1/products/?page=1"


def test_product_list_response_pagination_defaults_none() -> None:
    """next and previous default to None when not provided."""
    response = ProductListResponse(count=1, results=[ProductListItem(**VALID_ITEM_DATA)])
    assert response.next is None
    assert response.previous is None


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
    """ComponentSelection.specs must be a ProductDetail instance."""
    selection = ComponentSelection(**VALID_SELECTION_DATA)
    assert isinstance(selection.specs, ProductDetail)
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
