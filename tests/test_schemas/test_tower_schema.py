"""Tests for the tower API Pydantic schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from orchestrator.schemas.tower import (
    RunTriggerRequest,
    RunTriggerResponse,
    TowerDetail,
    TowerListResponse,
    TowerSummary,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_HASH = "abc123def456" * 4  # 48-char stand-in for a SHA-256 hash
_NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# TowerSummary
# ---------------------------------------------------------------------------


def test_tower_summary_valid() -> None:
    """Valid data creates a TowerSummary with all fields set correctly."""
    summary = TowerSummary(
        bundle_hash=_HASH,
        category="Gaming",
        status="Active",
        ml_id="ML-001",
        total_price=1299.99,
        created_at=_NOW,
    )

    assert summary.bundle_hash == _HASH
    assert summary.category == "Gaming"
    assert summary.status == "Active"
    assert summary.ml_id == "ML-001"
    assert summary.total_price == 1299.99
    assert summary.created_at == _NOW


def test_tower_summary_ml_id_none() -> None:
    """TowerSummary accepts None for the optional ml_id field."""
    summary = TowerSummary(
        bundle_hash=_HASH,
        category="Home",
        status="Paused",
        ml_id=None,
        total_price=599.00,
        created_at=_NOW,
    )

    assert summary.ml_id is None


def test_tower_summary_missing_required_fields() -> None:
    """Missing required fields raise a ValidationError."""
    with pytest.raises(ValidationError):
        TowerSummary(bundle_hash=_HASH)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# TowerDetail
# ---------------------------------------------------------------------------


def test_tower_detail_valid() -> None:
    """Valid data creates a TowerDetail with component_skus and timestamps."""
    skus: dict[str, str] = {"cpu": "CPU-SKU-001", "ram": "RAM-SKU-002"}
    detail = TowerDetail(
        bundle_hash=_HASH,
        category="Business",
        status="Active",
        ml_id=None,
        component_skus=skus,
        total_price=899.50,
        created_at=_NOW,
        updated_at=_NOW,
    )

    assert detail.bundle_hash == _HASH
    assert detail.category == "Business"
    assert detail.component_skus == skus
    assert detail.updated_at == _NOW


def test_tower_detail_missing_updated_at() -> None:
    """Omitting updated_at raises a ValidationError."""
    with pytest.raises(ValidationError):
        TowerDetail(
            bundle_hash=_HASH,
            category="Home",
            status="Active",
            ml_id=None,
            component_skus={},
            total_price=0.0,
            created_at=_NOW,
            # updated_at intentionally omitted
        )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# TowerListResponse
# ---------------------------------------------------------------------------


def test_tower_list_response_valid() -> None:
    """TowerListResponse holds a count and a list of TowerSummary objects."""
    summary = TowerSummary(
        bundle_hash=_HASH,
        category="Gaming",
        status="Active",
        ml_id=None,
        total_price=1500.00,
        created_at=_NOW,
    )
    response = TowerListResponse(count=1, towers=[summary])

    assert response.count == 1
    assert len(response.towers) == 1
    assert response.towers[0].bundle_hash == _HASH


def test_tower_list_response_empty() -> None:
    """TowerListResponse with zero towers is valid."""
    response = TowerListResponse(count=0, towers=[])

    assert response.count == 0
    assert response.towers == []


# ---------------------------------------------------------------------------
# RunTriggerRequest
# ---------------------------------------------------------------------------


def test_run_trigger_request_defaults() -> None:
    """Default tiers include all three standard tiers: Home, Business, Gaming."""
    request = RunTriggerRequest()

    assert request.tiers == ["Home", "Business", "Gaming"]


def test_run_trigger_request_custom_tiers() -> None:
    """Custom tiers override the default list."""
    request = RunTriggerRequest(tiers=["Gaming"])

    assert request.tiers == ["Gaming"]


def test_run_trigger_request_empty_tiers() -> None:
    """An empty tiers list is accepted (caller's responsibility to validate)."""
    request = RunTriggerRequest(tiers=[])

    assert request.tiers == []


# ---------------------------------------------------------------------------
# RunTriggerResponse
# ---------------------------------------------------------------------------


def test_run_trigger_response_valid() -> None:
    """Valid response schema serialization round-trips correctly."""
    response = RunTriggerResponse(
        status="completed",
        towers_created=3,
        tower_hashes=["hash1", "hash2", "hash3"],
        errors=[],
    )

    assert response.status == "completed"
    assert response.towers_created == 3
    assert len(response.tower_hashes) == 3
    assert response.errors == []


def test_run_trigger_response_errors_default() -> None:
    """errors field defaults to an empty list when not provided."""
    response = RunTriggerResponse(
        status="partial",
        towers_created=1,
        tower_hashes=["hash1"],
    )

    assert response.errors == []


def test_run_trigger_response_with_errors() -> None:
    """errors field captures error messages from a failed run."""
    response = RunTriggerResponse(
        status="failed",
        towers_created=0,
        tower_hashes=[],
        errors=["Compatibility check failed for Gaming tier"],
    )

    assert response.errors == ["Compatibility check failed for Gaming tier"]
    assert response.towers_created == 0


def test_run_trigger_response_serialization() -> None:
    """RunTriggerResponse serializes to a plain dict correctly."""
    response = RunTriggerResponse(
        status="completed",
        towers_created=2,
        tower_hashes=["hashA", "hashB"],
    )
    data = response.model_dump()

    assert data["status"] == "completed"
    assert data["towers_created"] == 2
    assert data["tower_hashes"] == ["hashA", "hashB"]
    assert data["errors"] == []
