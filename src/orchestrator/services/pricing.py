"""Pricing calculator for assembled PC builds.

Implements FR-4.1 and FR-4.2: computes the final listing price using the
formula ``Sum(component prices) x (1 + margin/100) x (1 + fee/100)``.

This module is pure logic with no external dependencies, making it
trivially testable and fully deterministic.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Component roles extracted from serialised TowerBuild dicts.
_COMPONENT_ROLES: tuple[str, ...] = (
    "cpu",
    "motherboard",
    "ram",
    "gpu",
    "ssd",
    "psu",
    "case",
)


class PricingCalculator:
    """Calculates final listing prices for assembled PC builds.

    Implements FR-4.1 and FR-4.2.

    Args:
        assembly_margin_percent: Assembly margin as a percentage (e.g., 15.0).
        ml_fee_percent: MercadoLibre fee as a percentage (e.g., 12.0).
    """

    def __init__(
        self,
        assembly_margin_percent: float,
        ml_fee_percent: float,
    ) -> None:
        self._margin_multiplier: float = 1.0 + assembly_margin_percent / 100.0
        self._fee_multiplier: float = 1.0 + ml_fee_percent / 100.0

    def calculate_tower_price(self, build: dict[str, object]) -> float:
        """Calculate final price for a tower build.

        Applies the pricing formula:
        ``Sum(component prices) x (1 + margin/100) x (1 + fee/100)``

        Args:
            build: Serialised ``TowerBuild`` dict from the Inventory Architect.

        Returns:
            Final tower price rounded to 2 decimal places.
        """
        base = self._sum_component_prices(build)
        return round(base * self._margin_multiplier * self._fee_multiplier, 2)

    def calculate_bundle_price(self, build: dict[str, object], bundle: dict[str, object]) -> float:
        """Calculate final price for a complete kit (tower + peripherals).

        Adds the ``total_peripheral_price`` from the bundle dict to the
        component sum before applying margin and fee multipliers.

        Args:
            build: Serialised ``TowerBuild`` dict from the Inventory Architect.
            bundle: Serialised ``BundleBuild`` dict containing peripheral data.

        Returns:
            Final bundle price rounded to 2 decimal places.
        """
        base = self._sum_component_prices(build)
        raw = bundle.get("total_peripheral_price", 0.0)
        peripheral_price = float(raw) if isinstance(raw, (int, float)) else 0.0
        total = base + peripheral_price
        return round(total * self._margin_multiplier * self._fee_multiplier, 2)

    def _sum_component_prices(self, build: dict[str, object]) -> float:
        """Sum all component prices from a build dict.

        Iterates over the standard component roles (cpu, motherboard, ram,
        gpu, ssd, psu, case) and sums their ``price`` values.  Components
        that are ``None`` (e.g., GPU for Home tier) are skipped.

        Args:
            build: Serialised ``TowerBuild`` dict from the Inventory Architect.

        Returns:
            Total component price as a float.
        """
        total: float = 0.0
        for role in _COMPONENT_ROLES:
            component = build.get(role)
            if component and isinstance(component, dict):
                total += float(component.get("price", 0.0))
        return total
