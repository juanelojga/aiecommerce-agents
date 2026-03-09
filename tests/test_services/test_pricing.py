"""Tests for the PricingCalculator service."""

from orchestrator.services.pricing import PricingCalculator

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

# Standard build dict with all components (Gaming tier).
_FULL_BUILD: dict[str, object] = {
    "tier": "Gaming",
    "cpu": {"normalized_name": "Intel Core i7-13700K", "price": 400.0},
    "motherboard": {"normalized_name": "ASUS ROG Strix Z790-E", "price": 350.0},
    "ram": {"normalized_name": "Corsair 32GB DDR5", "price": 120.0},
    "gpu": {"normalized_name": "NVIDIA RTX 4080", "price": 1200.0},
    "ssd": {"normalized_name": "Samsung 990 Pro 2TB", "price": 180.0},
    "psu": {"normalized_name": "Corsair RM850x", "price": 130.0},
    "case": {"normalized_name": "NZXT H510", "price": 80.0},
}

# Home tier build without a GPU.
_NO_GPU_BUILD: dict[str, object] = {
    "tier": "Home",
    "cpu": {"normalized_name": "AMD Ryzen 5 5600X", "price": 200.0},
    "motherboard": {"normalized_name": "MSI B550 Tomahawk", "price": 150.0},
    "ram": {"normalized_name": "Kingston 16GB DDR4", "price": 60.0},
    "gpu": None,
    "ssd": {"normalized_name": "WD Blue 1TB", "price": 80.0},
    "psu": {"normalized_name": "EVGA 650W", "price": 70.0},
    "case": {"normalized_name": "Fractal Design Pop Air", "price": 60.0},
}

# Bundle dict with peripheral total price.
_BUNDLE: dict[str, object] = {
    "tier": "Gaming",
    "tower_hash": "abc123",
    "bundle_id": "bundle-xyz",
    "total_peripheral_price": 500.0,
    "peripherals": [
        {"normalized_name": "LG 27GP850-B 27 QHD", "category": "monitor", "price": 300.0},
        {"normalized_name": "Logitech G Pro X", "category": "keyboard", "price": 120.0},
        {"normalized_name": "Logitech G502 X", "category": "mouse", "price": 80.0},
    ],
}


# ---------------------------------------------------------------------------
# Tests: _sum_component_prices
# ---------------------------------------------------------------------------


class TestSumComponentPrices:
    """Tests for ``PricingCalculator._sum_component_prices``."""

    def test_sum_component_prices_all_roles(self) -> None:
        """Sums CPU, MB, RAM, GPU, SSD, PSU, Case prices."""
        calc = PricingCalculator(assembly_margin_percent=0.0, ml_fee_percent=0.0)
        total = calc._sum_component_prices(_FULL_BUILD)
        # 400 + 350 + 120 + 1200 + 180 + 130 + 80 = 2460
        assert total == 2460.0

    def test_sum_component_prices_no_gpu(self) -> None:
        """Handles builds without GPU (GPU is optional for Home tier)."""
        calc = PricingCalculator(assembly_margin_percent=0.0, ml_fee_percent=0.0)
        total = calc._sum_component_prices(_NO_GPU_BUILD)
        # 200 + 150 + 60 + 80 + 70 + 60 = 620
        assert total == 620.0


# ---------------------------------------------------------------------------
# Tests: calculate_tower_price
# ---------------------------------------------------------------------------


class TestCalculateTowerPrice:
    """Tests for ``PricingCalculator.calculate_tower_price``."""

    def test_calculate_tower_price_basic(self) -> None:
        """Correct price with known components (zero margin and fee)."""
        calc = PricingCalculator(assembly_margin_percent=0.0, ml_fee_percent=0.0)
        price = calc.calculate_tower_price(_FULL_BUILD)
        assert price == 2460.0

    def test_calculate_tower_price_margin_applied(self) -> None:
        """Assembly margin applied correctly."""
        calc = PricingCalculator(assembly_margin_percent=10.0, ml_fee_percent=0.0)
        price = calc.calculate_tower_price(_FULL_BUILD)
        # 2460 * 1.10 = 2706.0
        assert price == 2706.0

    def test_calculate_tower_price_ml_fee_applied(self) -> None:
        """ML fee applied on top of margin."""
        calc = PricingCalculator(assembly_margin_percent=10.0, ml_fee_percent=5.0)
        price = calc.calculate_tower_price(_FULL_BUILD)
        # 2460 * 1.10 * 1.05 = 2841.30
        assert price == 2841.30

    def test_calculate_tower_price_rounding(self) -> None:
        """Result rounded to 2 decimal places."""
        # Pick values that produce a repeating decimal.
        calc = PricingCalculator(assembly_margin_percent=15.0, ml_fee_percent=12.0)
        price = calc.calculate_tower_price(_FULL_BUILD)
        # 2460 * 1.15 * 1.12 = 3168.48
        assert price == round(2460.0 * 1.15 * 1.12, 2)
        # Verify it's exactly 2 decimal places.
        assert price == round(price, 2)

    def test_calculate_tower_price_zero_margin(self) -> None:
        """Works with 0% margin (only fee applied)."""
        calc = PricingCalculator(assembly_margin_percent=0.0, ml_fee_percent=12.0)
        price = calc.calculate_tower_price(_FULL_BUILD)
        # 2460 * 1.0 * 1.12 = 2755.20
        assert price == 2755.20

    def test_calculate_tower_price_zero_fee(self) -> None:
        """Works with 0% fee (only margin applied)."""
        calc = PricingCalculator(assembly_margin_percent=15.0, ml_fee_percent=0.0)
        price = calc.calculate_tower_price(_FULL_BUILD)
        # 2460 * 1.15 * 1.0 = 2829.0
        assert price == 2829.0


# ---------------------------------------------------------------------------
# Tests: calculate_bundle_price
# ---------------------------------------------------------------------------


class TestCalculateBundlePrice:
    """Tests for ``PricingCalculator.calculate_bundle_price``."""

    def test_calculate_bundle_price_includes_peripherals(self) -> None:
        """Bundle price includes peripheral costs."""
        calc = PricingCalculator(assembly_margin_percent=10.0, ml_fee_percent=5.0)
        price = calc.calculate_bundle_price(_FULL_BUILD, _BUNDLE)
        # Components: 2460, peripherals: 500, total base: 2960
        # 2960 * 1.10 * 1.05 = 3418.80
        assert price == 3418.80
