"""Tests for the bundle Pydantic schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from orchestrator.schemas.bundle import (
    BundleBuild,
    BundleDetail,
    BundleListResponse,
    BundleSummary,
    PeripheralCategory,
    PeripheralSelection,
)
from orchestrator.schemas.product import ComponentCategory, ProductDetail

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_BUNDLE_ID = "deadbeef" * 8  # 64-char stand-in for a SHA-256 hash
_TOWER_HASH = "cafebabe" * 8  # 64-char stand-in for a SHA-256 hash
_NOW = datetime(2025, 6, 1, 10, 0, 0, tzinfo=UTC)

_PRODUCT_DETAIL = ProductDetail(
    id=1,
    code="KB-001",
    sku="KB-SKU-001",
    normalized_name="Mechanical Keyboard",
    price=79.99,
    category=ComponentCategory.KEYBOARD,
)


# ---------------------------------------------------------------------------
# PeripheralCategory
# ---------------------------------------------------------------------------


def test_peripheral_category_enum_values() -> None:
    """All 4 peripheral categories are present with the correct string values."""
    assert PeripheralCategory.KEYBOARD.value == "keyboard"
    assert PeripheralCategory.MOUSE.value == "mouse"
    assert PeripheralCategory.MONITOR.value == "monitor"
    assert PeripheralCategory.SPEAKERS.value == "speakers"
    assert len(PeripheralCategory) == 4


# ---------------------------------------------------------------------------
# PeripheralSelection
# ---------------------------------------------------------------------------


def test_peripheral_selection_valid() -> None:
    """Valid data creates a PeripheralSelection with all fields set correctly."""
    selection = PeripheralSelection(
        sku="KB-SKU-001",
        normalized_name="Mechanical Keyboard",
        category=PeripheralCategory.KEYBOARD,
        price=79.99,
        specs=_PRODUCT_DETAIL,
    )

    assert selection.sku == "KB-SKU-001"
    assert selection.normalized_name == "Mechanical Keyboard"
    assert selection.category == PeripheralCategory.KEYBOARD
    assert selection.price == 79.99
    assert selection.specs == _PRODUCT_DETAIL


# ---------------------------------------------------------------------------
# BundleBuild
# ---------------------------------------------------------------------------


def test_bundle_build_defaults() -> None:
    """BundleBuild defaults: bundle_id is empty string, total_peripheral_price is 0.0."""
    build = BundleBuild(
        tower_hash=_TOWER_HASH,
        tier="Home",
        peripherals=[],
    )

    assert build.bundle_id == ""
    assert build.total_peripheral_price == 0.0


def test_bundle_build_with_peripherals() -> None:
    """BundleBuild serializes a list of peripherals correctly."""
    keyboard = PeripheralSelection(
        sku="KB-SKU-001",
        normalized_name="Mechanical Keyboard",
        category=PeripheralCategory.KEYBOARD,
        price=79.99,
        specs=_PRODUCT_DETAIL,
    )
    mouse_detail = ProductDetail(
        id=2,
        code="MS-001",
        sku="MS-SKU-001",
        normalized_name="Gaming Mouse",
        price=49.99,
        category=ComponentCategory.MOUSE,
    )
    mouse = PeripheralSelection(
        sku="MS-SKU-001",
        normalized_name="Gaming Mouse",
        category=PeripheralCategory.MOUSE,
        price=49.99,
        specs=mouse_detail,
    )
    build = BundleBuild(
        tower_hash=_TOWER_HASH,
        tier="Gaming",
        peripherals=[keyboard, mouse],
        bundle_id=_BUNDLE_ID,
        total_peripheral_price=129.98,
    )

    assert len(build.peripherals) == 2
    assert build.peripherals[0].sku == "KB-SKU-001"
    assert build.peripherals[1].category == PeripheralCategory.MOUSE
    assert build.bundle_id == _BUNDLE_ID
    assert build.total_peripheral_price == 129.98


# ---------------------------------------------------------------------------
# BundleSummary
# ---------------------------------------------------------------------------


def test_bundle_summary_valid() -> None:
    """Valid data creates a BundleSummary with all fields set correctly."""
    summary = BundleSummary(
        bundle_id=_BUNDLE_ID,
        tower_hash=_TOWER_HASH,
        peripheral_skus={"keyboard": "KB-SKU-001"},
        ml_id="ML-100",
        created_at=_NOW,
    )

    assert summary.bundle_id == _BUNDLE_ID
    assert summary.tower_hash == _TOWER_HASH
    assert summary.peripheral_skus == {"keyboard": "KB-SKU-001"}
    assert summary.ml_id == "ML-100"
    assert summary.created_at == _NOW


def test_bundle_summary_ml_id_none() -> None:
    """BundleSummary accepts None for the optional ml_id field."""
    summary = BundleSummary(
        bundle_id=_BUNDLE_ID,
        tower_hash=_TOWER_HASH,
        peripheral_skus={},
        ml_id=None,
        created_at=_NOW,
    )

    assert summary.ml_id is None


# ---------------------------------------------------------------------------
# BundleDetail
# ---------------------------------------------------------------------------


def test_bundle_detail_valid() -> None:
    """Valid data creates a BundleDetail with all fields including updated_at."""
    detail = BundleDetail(
        bundle_id=_BUNDLE_ID,
        tower_hash=_TOWER_HASH,
        peripheral_skus={"monitor": "MON-SKU-001"},
        ml_id=None,
        created_at=_NOW,
        updated_at=_NOW,
    )

    assert detail.bundle_id == _BUNDLE_ID
    assert detail.tower_hash == _TOWER_HASH
    assert detail.peripheral_skus == {"monitor": "MON-SKU-001"}
    assert detail.updated_at == _NOW


def test_bundle_detail_missing_updated_at() -> None:
    """Omitting updated_at raises a ValidationError."""
    with pytest.raises(ValidationError):
        BundleDetail(
            bundle_id=_BUNDLE_ID,
            tower_hash=_TOWER_HASH,
            peripheral_skus={},
            ml_id=None,
            created_at=_NOW,
            # updated_at intentionally omitted
        )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# BundleListResponse
# ---------------------------------------------------------------------------


def test_bundle_list_response_valid() -> None:
    """BundleListResponse holds a count and a list of BundleSummary objects."""
    summary = BundleSummary(
        bundle_id=_BUNDLE_ID,
        tower_hash=_TOWER_HASH,
        peripheral_skus={"keyboard": "KB-SKU-001"},
        ml_id=None,
        created_at=_NOW,
    )
    response = BundleListResponse(count=1, bundles=[summary])

    assert response.count == 1
    assert len(response.bundles) == 1
    assert response.bundles[0].bundle_id == _BUNDLE_ID


def test_bundle_list_response_empty() -> None:
    """BundleListResponse with an empty bundles list is valid."""
    response = BundleListResponse(count=0, bundles=[])

    assert response.count == 0
    assert response.bundles == []
