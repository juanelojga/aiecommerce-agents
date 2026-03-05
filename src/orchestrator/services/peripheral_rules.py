"""Tier-specific peripheral requirements configuration for the Bundle Creator.

Defines which peripheral categories are required per tier and the selection
strategy to use when picking from available products.

This module is the rule set that the Bundle Creator node uses for deterministic
peripheral selection (FR-2.2).
"""

from dataclasses import dataclass, field
from typing import Literal

from orchestrator.schemas.bundle import PeripheralCategory

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TierPeripheralSpec:
    """Peripheral requirements for a given tier.

    Attributes:
        required_categories: Tuple of peripheral categories required for this tier.
        selection_strategy: How to pick from available products
            (``"cheapest"`` / ``"balanced"`` / ``"premium"``).
        filter_tags: Optional spec filters per category
            (e.g. ``["144hz", "high-refresh"]`` for Gaming monitors).
    """

    required_categories: tuple[PeripheralCategory, ...]
    selection_strategy: Literal["cheapest", "balanced", "premium"]
    filter_tags: dict[PeripheralCategory, list[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tier configurations
# ---------------------------------------------------------------------------

TIER_PERIPHERAL_SPECS: dict[str, TierPeripheralSpec] = {
    "Home": TierPeripheralSpec(
        required_categories=(
            PeripheralCategory.KEYBOARD,
            PeripheralCategory.MOUSE,
            PeripheralCategory.MONITOR,
        ),
        selection_strategy="cheapest",
        filter_tags={},
    ),
    "Business": TierPeripheralSpec(
        required_categories=(
            PeripheralCategory.KEYBOARD,
            PeripheralCategory.MOUSE,
            PeripheralCategory.MONITOR,
        ),
        selection_strategy="balanced",
        filter_tags={},
    ),
    "Gaming": TierPeripheralSpec(
        required_categories=(
            PeripheralCategory.KEYBOARD,
            PeripheralCategory.MOUSE,
            PeripheralCategory.MONITOR,
            PeripheralCategory.SPEAKERS,
        ),
        selection_strategy="premium",
        filter_tags={PeripheralCategory.MONITOR: ["144hz", "high-refresh"]},
    ),
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_KNOWN_TIERS = ", ".join(sorted(TIER_PERIPHERAL_SPECS))


def get_tier_spec(tier: str) -> TierPeripheralSpec:
    """Get peripheral requirements for a given tier.

    Args:
        tier: Target tier name (``"Home"``, ``"Business"``, or ``"Gaming"``).

    Returns:
        The :class:`TierPeripheralSpec` for the requested tier.

    Raises:
        ValueError: If the tier name is not recognised.
    """
    try:
        return TIER_PERIPHERAL_SPECS[tier]
    except KeyError:
        raise ValueError(f"Unknown tier '{tier}'. Known tiers are: {_KNOWN_TIERS}.") from None
