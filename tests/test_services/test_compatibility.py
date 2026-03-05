"""Tests for the deterministic compatibility validation engine."""

import pytest

from orchestrator.core.exceptions import CompatibilityError
from orchestrator.schemas.product import (
    ComponentCategory,
    ComponentSelection,
    ProductDetail,
    TowerBuild,
)
from orchestrator.services.compatibility import CompatibilityEngine

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _make_product_detail(
    category: ComponentCategory,
    sku: str,
    specs: dict[str, object] | None = None,
) -> ProductDetail:
    """Return a minimal ``ProductDetail`` with optional spec overrides.

    Args:
        category: Component category enum value.
        sku: SKU string used for ``id``, ``code``, and ``sku`` fields.
        specs: Technical spec dictionary to embed.  Defaults to empty dict.

    Returns:
        A populated :class:`~orchestrator.schemas.product.ProductDetail`.
    """
    return ProductDetail(
        id=1,
        code=sku,
        sku=sku,
        normalized_name=sku,
        price=0.0,
        category=category,
        specs=specs or {},
    )


def _make_selection(
    category: ComponentCategory,
    sku: str,
    price: float = 100.0,
    specs: dict[str, object] | None = None,
) -> ComponentSelection:
    """Return a :class:`~orchestrator.schemas.product.ComponentSelection`.

    Args:
        category: Component category.
        sku: SKU identifier.
        price: Unit price (default ``100.0``).
        specs: Technical spec overrides for the embedded ``ProductDetail``.

    Returns:
        A populated :class:`~orchestrator.schemas.product.ComponentSelection`.
    """
    return ComponentSelection(
        sku=sku,
        normalized_name=f"Component {sku}",
        category=category,
        price=price,
        specs=_make_product_detail(category, sku, specs),
    )


def _make_valid_build(
    cpu_socket: str = "AM5",
    mb_socket: str = "AM5",
    ram_type: str = "DDR5",
    mb_memory: str = "DDR5",
    ssd_interface: str = "M.2",
    mb_ssd_interfaces: list[str] | None = None,
    cpu_tdp: float = 125.0,
    gpu_tdp: float = 200.0,
    psu_wattage: float = 400.0,
    case_ff: str = "ATX",
    mb_ff: str = "ATX",
) -> TowerBuild:
    """Build a :class:`~orchestrator.schemas.product.TowerBuild` with configurable specs.

    Args:
        cpu_socket: CPU socket string.
        mb_socket: Motherboard socket string.
        ram_type: RAM memory type (e.g. ``"DDR5"``).
        mb_memory: Motherboard supported memory type.
        ssd_interface: SSD interface string.
        mb_ssd_interfaces: List of interfaces supported by the motherboard.
        cpu_tdp: CPU TDP in watts.
        gpu_tdp: GPU TDP in watts.
        psu_wattage: PSU rated wattage.
        case_ff: Case form factor string.
        mb_ff: Motherboard form factor string.

    Returns:
        A fully populated :class:`~orchestrator.schemas.product.TowerBuild`.
    """
    supported_ssd: list[str] = (
        mb_ssd_interfaces if mb_ssd_interfaces is not None else ["M.2", "SATA"]
    )

    return TowerBuild(
        tier="Home",
        cpu=_make_selection(
            ComponentCategory.CPU, "CPU-001", specs={"socket": cpu_socket, "tdp": cpu_tdp}
        ),
        motherboard=_make_selection(
            ComponentCategory.MOTHERBOARD,
            "MB-001",
            specs={
                "socket": mb_socket,
                "memory_type": mb_memory,
                "supported_ssd_interfaces": supported_ssd,
                "form_factor": mb_ff,
            },
        ),
        ram=_make_selection(ComponentCategory.RAM, "RAM-001", specs={"memory_type": ram_type}),
        gpu=_make_selection(ComponentCategory.GPU, "GPU-001", specs={"tdp": gpu_tdp}),
        ssd=_make_selection(ComponentCategory.SSD, "SSD-001", specs={"interface": ssd_interface}),
        psu=_make_selection(ComponentCategory.PSU, "PSU-001", specs={"wattage": psu_wattage}),
        case=_make_selection(ComponentCategory.CASE, "CASE-001", specs={"form_factor": case_ff}),
    )


# ---------------------------------------------------------------------------
# CompatibilityEngine.validate_build
# ---------------------------------------------------------------------------


class TestValidateBuild:
    """Tests for ``CompatibilityEngine.validate_build``."""

    def test_valid_build_passes(self) -> None:
        """Fully compatible build returns an empty error list."""
        engine = CompatibilityEngine()
        # cpu_tdp + gpu_tdp = 325 W; PSU 400 W => 400 >= 325 * 1.2 = 390 W — OK.
        build = _make_valid_build(
            cpu_tdp=125.0,
            gpu_tdp=200.0,
            psu_wattage=400.0,
        )
        assert engine.validate_build(build) == []

    def test_validate_build_multiple_errors(self) -> None:
        """Multiple incompatibilities are all collected in a single pass."""
        engine = CompatibilityEngine()
        build = _make_valid_build(
            cpu_socket="AM5",
            mb_socket="LGA1700",  # socket mismatch
            ram_type="DDR4",
            mb_memory="DDR5",  # RAM mismatch
        )
        errors = engine.validate_build(build)
        assert len(errors) == 2
        assert any("socket" in e.lower() for e in errors)
        assert any("memory type" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# CompatibilityEngine.validate_socket
# ---------------------------------------------------------------------------


class TestValidateSocket:
    """Tests for ``CompatibilityEngine.validate_socket``."""

    def test_socket_match_passes(self) -> None:
        """Matching sockets return ``None``."""
        engine = CompatibilityEngine()
        cpu = _make_selection(ComponentCategory.CPU, "CPU-001", specs={"socket": "AM5"})
        mb = _make_selection(ComponentCategory.MOTHERBOARD, "MB-001", specs={"socket": "AM5"})
        assert engine.validate_socket(cpu, mb) is None

    def test_socket_mismatch(self) -> None:
        """Mismatched CPU/MB socket yields an error message."""
        engine = CompatibilityEngine()
        cpu = _make_selection(ComponentCategory.CPU, "CPU-001", specs={"socket": "AM5"})
        mb = _make_selection(ComponentCategory.MOTHERBOARD, "MB-001", specs={"socket": "LGA1700"})
        result = engine.validate_socket(cpu, mb)
        assert result is not None
        assert "AM5" in result
        assert "LGA1700" in result

    def test_socket_missing_cpu_spec_skips(self) -> None:
        """Missing CPU socket spec skips the rule (returns ``None``)."""
        engine = CompatibilityEngine()
        cpu = _make_selection(ComponentCategory.CPU, "CPU-001", specs={})
        mb = _make_selection(ComponentCategory.MOTHERBOARD, "MB-001", specs={"socket": "AM5"})
        assert engine.validate_socket(cpu, mb) is None

    def test_socket_missing_mb_spec_skips(self) -> None:
        """Missing MB socket spec skips the rule (returns ``None``)."""
        engine = CompatibilityEngine()
        cpu = _make_selection(ComponentCategory.CPU, "CPU-001", specs={"socket": "AM5"})
        mb = _make_selection(ComponentCategory.MOTHERBOARD, "MB-001", specs={})
        assert engine.validate_socket(cpu, mb) is None

    def test_socket_case_insensitive(self) -> None:
        """Socket comparison is case-insensitive."""
        engine = CompatibilityEngine()
        cpu = _make_selection(ComponentCategory.CPU, "CPU-001", specs={"socket": "am5"})
        mb = _make_selection(ComponentCategory.MOTHERBOARD, "MB-001", specs={"socket": "AM5"})
        assert engine.validate_socket(cpu, mb) is None


# ---------------------------------------------------------------------------
# CompatibilityEngine.validate_ram
# ---------------------------------------------------------------------------


class TestValidateRam:
    """Tests for ``CompatibilityEngine.validate_ram``."""

    def test_ram_match_passes(self) -> None:
        """Matching DDR types return ``None``."""
        engine = CompatibilityEngine()
        ram = _make_selection(ComponentCategory.RAM, "RAM-001", specs={"memory_type": "DDR5"})
        mb = _make_selection(ComponentCategory.MOTHERBOARD, "MB-001", specs={"memory_type": "DDR5"})
        assert engine.validate_ram(ram, mb) is None

    def test_ram_ddr_mismatch(self) -> None:
        """DDR4 RAM on a DDR5-only board yields an error message."""
        engine = CompatibilityEngine()
        ram = _make_selection(ComponentCategory.RAM, "RAM-001", specs={"memory_type": "DDR4"})
        mb = _make_selection(ComponentCategory.MOTHERBOARD, "MB-001", specs={"memory_type": "DDR5"})
        result = engine.validate_ram(ram, mb)
        assert result is not None
        assert "DDR4" in result
        assert "DDR5" in result

    def test_ram_missing_spec_skips(self) -> None:
        """Missing memory_type spec on either component skips the rule."""
        engine = CompatibilityEngine()
        ram = _make_selection(ComponentCategory.RAM, "RAM-001", specs={})
        mb = _make_selection(ComponentCategory.MOTHERBOARD, "MB-001", specs={"memory_type": "DDR5"})
        assert engine.validate_ram(ram, mb) is None


# ---------------------------------------------------------------------------
# CompatibilityEngine.validate_ssd
# ---------------------------------------------------------------------------


class TestValidateSsd:
    """Tests for ``CompatibilityEngine.validate_ssd``."""

    def test_ssd_interface_match_passes(self) -> None:
        """Matching SSD interface returns ``None``."""
        engine = CompatibilityEngine()
        ssd = _make_selection(ComponentCategory.SSD, "SSD-001", specs={"interface": "M.2"})
        mb = _make_selection(
            ComponentCategory.MOTHERBOARD,
            "MB-001",
            specs={"supported_ssd_interfaces": ["M.2", "SATA"]},
        )
        assert engine.validate_ssd(ssd, mb) is None

    def test_ssd_interface_mismatch(self) -> None:
        """M.2 SSD on a board without an M.2 slot yields an error message."""
        engine = CompatibilityEngine()
        ssd = _make_selection(ComponentCategory.SSD, "SSD-001", specs={"interface": "M.2"})
        mb = _make_selection(
            ComponentCategory.MOTHERBOARD,
            "MB-001",
            specs={"supported_ssd_interfaces": ["SATA"]},
        )
        result = engine.validate_ssd(ssd, mb)
        assert result is not None
        assert "M.2" in result

    def test_ssd_missing_interface_skips(self) -> None:
        """Missing interface key on SSD skips the rule."""
        engine = CompatibilityEngine()
        ssd = _make_selection(ComponentCategory.SSD, "SSD-001", specs={})
        mb = _make_selection(
            ComponentCategory.MOTHERBOARD,
            "MB-001",
            specs={"supported_ssd_interfaces": ["M.2"]},
        )
        assert engine.validate_ssd(ssd, mb) is None

    def test_ssd_missing_mb_interfaces_skips(self) -> None:
        """Missing supported_ssd_interfaces on motherboard skips the rule."""
        engine = CompatibilityEngine()
        ssd = _make_selection(ComponentCategory.SSD, "SSD-001", specs={"interface": "M.2"})
        mb = _make_selection(ComponentCategory.MOTHERBOARD, "MB-001", specs={})
        assert engine.validate_ssd(ssd, mb) is None

    def test_ssd_interface_string_value(self) -> None:
        """A plain string (not a list) for supported interfaces is accepted."""
        engine = CompatibilityEngine()
        ssd = _make_selection(ComponentCategory.SSD, "SSD-001", specs={"interface": "SATA"})
        mb = _make_selection(
            ComponentCategory.MOTHERBOARD,
            "MB-001",
            specs={"supported_ssd_interfaces": "SATA"},
        )
        assert engine.validate_ssd(ssd, mb) is None


# ---------------------------------------------------------------------------
# CompatibilityEngine.validate_psu
# ---------------------------------------------------------------------------


class TestValidatePsu:
    """Tests for ``CompatibilityEngine.validate_psu``."""

    def test_psu_wattage_sufficient_with_headroom(self) -> None:
        """PSU providing exactly ≥20 % headroom over total TDP passes."""
        engine = CompatibilityEngine()
        # cpu_tdp=100, gpu_tdp=200, total=300, required=300*1.2=360 W.
        build = _make_valid_build(cpu_tdp=100.0, gpu_tdp=200.0, psu_wattage=360.0)
        assert engine.validate_psu(build.psu, build) is None

    def test_psu_wattage_insufficient(self) -> None:
        """PSU below required wattage (total TDP + 20 %) yields an error message."""
        engine = CompatibilityEngine()
        # cpu_tdp=100, gpu_tdp=200, total=300, required=360; PSU=359 → fail.
        build = _make_valid_build(cpu_tdp=100.0, gpu_tdp=200.0, psu_wattage=359.0)
        result = engine.validate_psu(build.psu, build)
        assert result is not None
        assert "359" in result
        assert "360" in result

    def test_psu_missing_wattage_skips(self) -> None:
        """Missing wattage spec on the PSU skips the rule."""
        engine = CompatibilityEngine()
        build = _make_valid_build()
        # Remove wattage from PSU specs.
        psu = _make_selection(ComponentCategory.PSU, "PSU-001", specs={})
        build_no_psu_spec = build.model_copy(update={"psu": psu})
        assert engine.validate_psu(build_no_psu_spec.psu, build_no_psu_spec) is None

    def test_psu_no_tdp_data_skips(self) -> None:
        """Missing TDP on both CPU and GPU skips the PSU rule."""
        engine = CompatibilityEngine()
        cpu = _make_selection(ComponentCategory.CPU, "CPU-001", specs={})
        build = _make_valid_build(psu_wattage=200.0)
        build_no_tdp = build.model_copy(update={"cpu": cpu, "gpu": None})
        assert engine.validate_psu(build_no_tdp.psu, build_no_tdp) is None

    def test_psu_no_gpu_uses_cpu_tdp_only(self) -> None:
        """PSU validation sums only CPU TDP when no GPU is present."""
        engine = CompatibilityEngine()
        # cpu_tdp=200, no GPU, required=200*1.2=240; PSU=239 → fail.
        build = _make_valid_build(cpu_tdp=200.0, gpu_tdp=0.0, psu_wattage=239.0)
        build_no_gpu = build.model_copy(update={"gpu": None})
        result = engine.validate_psu(build_no_gpu.psu, build_no_gpu)
        assert result is not None
        assert "239" in result


# ---------------------------------------------------------------------------
# CompatibilityEngine.validate_form_factor
# ---------------------------------------------------------------------------


class TestValidateFormFactor:
    """Tests for ``CompatibilityEngine.validate_form_factor``."""

    def test_form_factor_atx_in_atx(self) -> None:
        """ATX board in an ATX case passes."""
        engine = CompatibilityEngine()
        case = _make_selection(ComponentCategory.CASE, "CASE-001", specs={"form_factor": "ATX"})
        mb = _make_selection(ComponentCategory.MOTHERBOARD, "MB-001", specs={"form_factor": "ATX"})
        assert engine.validate_form_factor(case, mb) is None

    def test_form_factor_matx_in_atx(self) -> None:
        """mATX board in an ATX case passes (downsizing allowed)."""
        engine = CompatibilityEngine()
        case = _make_selection(ComponentCategory.CASE, "CASE-001", specs={"form_factor": "ATX"})
        mb = _make_selection(ComponentCategory.MOTHERBOARD, "MB-001", specs={"form_factor": "MATX"})
        assert engine.validate_form_factor(case, mb) is None

    def test_form_factor_itx_in_atx(self) -> None:
        """ITX board in an ATX case passes (downsizing allowed)."""
        engine = CompatibilityEngine()
        case = _make_selection(ComponentCategory.CASE, "CASE-001", specs={"form_factor": "ATX"})
        mb = _make_selection(ComponentCategory.MOTHERBOARD, "MB-001", specs={"form_factor": "ITX"})
        assert engine.validate_form_factor(case, mb) is None

    def test_form_factor_mismatch(self) -> None:
        """ATX board in an ITX case yields an error message."""
        engine = CompatibilityEngine()
        case = _make_selection(ComponentCategory.CASE, "CASE-001", specs={"form_factor": "ITX"})
        mb = _make_selection(ComponentCategory.MOTHERBOARD, "MB-001", specs={"form_factor": "ATX"})
        result = engine.validate_form_factor(case, mb)
        assert result is not None
        assert "ATX" in result
        assert "ITX" in result

    def test_form_factor_atx_in_matx_fails(self) -> None:
        """ATX board does not fit in an mATX case."""
        engine = CompatibilityEngine()
        case = _make_selection(ComponentCategory.CASE, "CASE-001", specs={"form_factor": "MATX"})
        mb = _make_selection(ComponentCategory.MOTHERBOARD, "MB-001", specs={"form_factor": "ATX"})
        result = engine.validate_form_factor(case, mb)
        assert result is not None

    def test_form_factor_missing_spec_skips(self) -> None:
        """Missing form_factor spec on either component skips the rule."""
        engine = CompatibilityEngine()
        case = _make_selection(ComponentCategory.CASE, "CASE-001", specs={})
        mb = _make_selection(ComponentCategory.MOTHERBOARD, "MB-001", specs={"form_factor": "ATX"})
        assert engine.validate_form_factor(case, mb) is None

    def test_form_factor_micro_atx_alias(self) -> None:
        """'MICRO-ATX' is treated as equivalent to 'MATX'."""
        engine = CompatibilityEngine()
        case = _make_selection(ComponentCategory.CASE, "CASE-001", specs={"form_factor": "ATX"})
        mb = _make_selection(
            ComponentCategory.MOTHERBOARD, "MB-001", specs={"form_factor": "MICRO-ATX"}
        )
        assert engine.validate_form_factor(case, mb) is None

    def test_form_factor_mini_itx_alias(self) -> None:
        """'MINI-ITX' is treated as equivalent to 'ITX'."""
        engine = CompatibilityEngine()
        case = _make_selection(ComponentCategory.CASE, "CASE-001", specs={"form_factor": "ATX"})
        mb = _make_selection(
            ComponentCategory.MOTHERBOARD, "MB-001", specs={"form_factor": "MINI-ITX"}
        )
        assert engine.validate_form_factor(case, mb) is None


# ---------------------------------------------------------------------------
# CompatibilityEngine.assert_valid
# ---------------------------------------------------------------------------


class TestAssertValid:
    """Tests for ``CompatibilityEngine.assert_valid``."""

    def test_assert_valid_passes_for_valid_build(self) -> None:
        """``assert_valid`` does not raise for a fully compatible build."""
        engine = CompatibilityEngine()
        # 125 + 200 = 325 W; 325 * 1.2 = 390; PSU = 400 W — OK.
        build = _make_valid_build(cpu_tdp=125.0, gpu_tdp=200.0, psu_wattage=400.0)
        engine.assert_valid(build)  # Should not raise.

    def test_assert_valid_raises_on_failure(self) -> None:
        """``assert_valid`` raises ``CompatibilityError`` when a rule fails."""
        engine = CompatibilityEngine()
        build = _make_valid_build(cpu_socket="AM5", mb_socket="LGA1700")
        with pytest.raises(CompatibilityError):
            engine.assert_valid(build)

    def test_assert_valid_message_contains_all_errors(self) -> None:
        """The ``CompatibilityError`` message contains details of every failure."""
        engine = CompatibilityEngine()
        # Trigger two failures: socket mismatch + RAM mismatch.
        build = _make_valid_build(
            cpu_socket="AM5",
            mb_socket="LGA1700",
            ram_type="DDR4",
            mb_memory="DDR5",
        )
        with pytest.raises(CompatibilityError) as exc_info:
            engine.assert_valid(build)

        message = str(exc_info.value)
        assert "socket" in message.lower()
        assert "memory type" in message.lower()
