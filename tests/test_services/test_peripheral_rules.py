"""Tests for the tier-specific peripheral requirements configuration."""

import pytest

from orchestrator.schemas.bundle import PeripheralCategory
from orchestrator.services.peripheral_rules import (
    TIER_PERIPHERAL_SPECS,
    TierPeripheralSpec,
    get_tier_spec,
)

# ---------------------------------------------------------------------------
# Home tier
# ---------------------------------------------------------------------------


def test_home_tier_categories() -> None:
    """Home tier requires keyboard, mouse, and monitor."""
    spec = TIER_PERIPHERAL_SPECS["Home"]
    assert PeripheralCategory.KEYBOARD in spec.required_categories
    assert PeripheralCategory.MOUSE in spec.required_categories
    assert PeripheralCategory.MONITOR in spec.required_categories
    assert len(spec.required_categories) == 3


def test_home_tier_strategy() -> None:
    """Home tier uses the cheapest selection strategy."""
    assert TIER_PERIPHERAL_SPECS["Home"].selection_strategy == "cheapest"


# ---------------------------------------------------------------------------
# Business tier
# ---------------------------------------------------------------------------


def test_business_tier_categories() -> None:
    """Business tier requires keyboard, mouse, and monitor."""
    spec = TIER_PERIPHERAL_SPECS["Business"]
    assert PeripheralCategory.KEYBOARD in spec.required_categories
    assert PeripheralCategory.MOUSE in spec.required_categories
    assert PeripheralCategory.MONITOR in spec.required_categories
    assert len(spec.required_categories) == 3


def test_business_tier_strategy() -> None:
    """Business tier uses the balanced selection strategy."""
    assert TIER_PERIPHERAL_SPECS["Business"].selection_strategy == "balanced"


# ---------------------------------------------------------------------------
# Gaming tier
# ---------------------------------------------------------------------------


def test_gaming_tier_categories() -> None:
    """Gaming tier requires keyboard, mouse, monitor, and speakers."""
    spec = TIER_PERIPHERAL_SPECS["Gaming"]
    assert PeripheralCategory.KEYBOARD in spec.required_categories
    assert PeripheralCategory.MOUSE in spec.required_categories
    assert PeripheralCategory.MONITOR in spec.required_categories
    assert PeripheralCategory.SPEAKERS in spec.required_categories
    assert len(spec.required_categories) == 4


def test_gaming_tier_strategy() -> None:
    """Gaming tier uses the premium selection strategy."""
    assert TIER_PERIPHERAL_SPECS["Gaming"].selection_strategy == "premium"


def test_gaming_monitor_filter_tags() -> None:
    """Gaming tier applies 144Hz / high-refresh filter tags to the monitor category."""
    tags = TIER_PERIPHERAL_SPECS["Gaming"].filter_tags
    assert PeripheralCategory.MONITOR in tags
    assert "144hz" in tags[PeripheralCategory.MONITOR]
    assert "high-refresh" in tags[PeripheralCategory.MONITOR]


# ---------------------------------------------------------------------------
# get_tier_spec
# ---------------------------------------------------------------------------


def test_get_tier_spec_valid() -> None:
    """get_tier_spec returns the correct TierPeripheralSpec for a valid tier."""
    for tier_name, expected_spec in TIER_PERIPHERAL_SPECS.items():
        result = get_tier_spec(tier_name)
        assert isinstance(result, TierPeripheralSpec)
        assert result is expected_spec


def test_get_tier_spec_invalid() -> None:
    """get_tier_spec raises ValueError for an unrecognised tier name."""
    with pytest.raises(ValueError, match="Unknown tier"):
        get_tier_spec("Ultra")
