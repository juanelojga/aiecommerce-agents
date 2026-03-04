"""Deterministic compatibility validation engine for tower builds.

Implements FR-1.3 compatibility rules:

- CPU socket matches motherboard socket.
- RAM DDR generation matches motherboard support.
- SSD interface is supported by the motherboard.
- PSU wattage covers total estimated TDP with 20 % headroom.
- Case form factor accommodates the motherboard (downsizing allowed).
"""

import logging

from orchestrator.core.exceptions import CompatibilityError
from orchestrator.schemas.product import ComponentSelection, TowerBuild

logger = logging.getLogger(__name__)

# Form factor hierarchy — higher rank means physically *smaller*.
# A case can host any motherboard whose rank is >= the case's own rank
# (same size or smaller).
_FORM_FACTOR_RANK: dict[str, int] = {
    "ATX": 0,
    "MATX": 1,
    "MICRO-ATX": 1,
    "MINI-ITX": 2,
    "MITX": 2,
    "ITX": 2,
}

# Minimum PSU headroom over total estimated TDP (20 %).
_PSU_HEADROOM: float = 0.20
_PSU_HEADROOM_PCT: int = int(_PSU_HEADROOM * 100)


def _get_float_spec(specs: dict[str, object], key: str) -> float | None:
    """Extract a numeric spec value and coerce it to ``float``.

    Returns ``None`` when the key is absent so callers can safely skip
    validation rules that depend on missing spec data.

    Args:
        specs: The component's technical specification dictionary.
        key: The spec key to look up.

    Returns:
        The value cast to ``float``, or ``None`` if the key is not present.
    """
    raw = specs.get(key)
    return float(str(raw)) if raw is not None else None


class CompatibilityEngine:
    """Validates technical compatibility of PC component selections.

    Rules enforced (FR-1.3):

    - CPU socket matches motherboard socket.
    - RAM DDR generation matches motherboard support.
    - SSD interface is supported by the motherboard.
    - PSU wattage covers estimated total TDP with 20 % headroom.
    - Case form factor accommodates the motherboard.

    The engine is a pure, stateless class with no external dependencies so
    it can be instantiated and tested without any I/O or database setup.
    """

    def validate_build(self, build: TowerBuild) -> list[str]:
        """Validate all compatibility rules for a build in a single pass.

        Args:
            build: The tower build to validate.

        Returns:
            A list of human-readable error messages; empty when the build is
            fully compatible.
        """
        errors: list[str] = []

        # Rule 1: CPU socket ↔ motherboard socket.
        if err := self.validate_socket(build.cpu, build.motherboard):
            errors.append(err)

        # Rule 2: RAM DDR generation ↔ motherboard memory type.
        if err := self.validate_ram(build.ram, build.motherboard):
            errors.append(err)

        # Rule 3: SSD interface ↔ motherboard supported interfaces.
        if err := self.validate_ssd(build.ssd, build.motherboard):
            errors.append(err)

        # Rule 4: PSU wattage ≥ total TDP + 20 % headroom.
        if err := self.validate_psu(build.psu, build):
            errors.append(err)

        # Rule 5: Case form factor accommodates the motherboard.
        if err := self.validate_form_factor(build.case, build.motherboard):
            errors.append(err)

        return errors

    def validate_socket(
        self, cpu: ComponentSelection, motherboard: ComponentSelection
    ) -> str | None:
        """Check CPU socket ↔ motherboard socket compatibility.

        Reads the ``socket`` key from each component's ``specs`` dictionary.
        If either component is missing this key the rule is skipped rather
        than raising a false-positive error.

        Args:
            cpu: The selected CPU component.
            motherboard: The selected motherboard component.

        Returns:
            An error message string when the sockets do not match, otherwise
            ``None``.
        """
        cpu_socket = str(cpu.specs.specs.get("socket", "")).upper()
        mb_socket = str(motherboard.specs.specs.get("socket", "")).upper()

        if not cpu_socket or not mb_socket:
            return None

        if cpu_socket != mb_socket:
            return (
                f"CPU socket '{cpu_socket}' is incompatible with motherboard socket '{mb_socket}'."
            )
        return None

    def validate_ram(self, ram: ComponentSelection, motherboard: ComponentSelection) -> str | None:
        """Check RAM DDR generation ↔ motherboard memory type support.

        Reads the ``memory_type`` key (e.g. ``"DDR4"``, ``"DDR5"``) from each
        component's ``specs`` dictionary.

        Args:
            ram: The selected RAM component.
            motherboard: The selected motherboard component.

        Returns:
            An error message string when the memory types are incompatible,
            otherwise ``None``.
        """
        ram_type = str(ram.specs.specs.get("memory_type", "")).upper()
        mb_memory = str(motherboard.specs.specs.get("memory_type", "")).upper()

        if not ram_type or not mb_memory:
            return None

        if ram_type != mb_memory:
            return (
                f"RAM memory type '{ram_type}' is incompatible with "
                f"motherboard memory type '{mb_memory}'."
            )
        return None

    def validate_ssd(self, ssd: ComponentSelection, motherboard: ComponentSelection) -> str | None:
        """Check SSD interface ↔ motherboard supported SSD interfaces.

        Reads the ``interface`` key from the SSD specs (e.g. ``"M.2"``,
        ``"SATA"``) and ``supported_ssd_interfaces`` (a list of strings) from
        the motherboard specs.

        Args:
            ssd: The selected SSD component.
            motherboard: The selected motherboard component.

        Returns:
            An error message string when the SSD interface is not supported,
            otherwise ``None``.
        """
        ssd_interface = str(ssd.specs.specs.get("interface", "")).upper()
        mb_interfaces_raw = motherboard.specs.specs.get("supported_ssd_interfaces")

        if not ssd_interface or mb_interfaces_raw is None:
            return None

        # Accept both a plain string and a list of strings.
        raw_list = mb_interfaces_raw if isinstance(mb_interfaces_raw, list) else [mb_interfaces_raw]
        mb_interfaces: list[str] = [str(i).upper() for i in raw_list]

        if ssd_interface not in mb_interfaces:
            return (
                f"SSD interface '{ssd_interface}' is not supported by the motherboard "
                f"(supported: {', '.join(mb_interfaces)})."
            )
        return None

    def validate_psu(self, psu: ComponentSelection, build: TowerBuild) -> str | None:
        """Check PSU wattage covers total estimated TDP with 20 % headroom.

        Aggregates ``tdp`` from the CPU and, when present, the GPU.  If TDP
        data is missing from both the rule is skipped.  PSU wattage is read
        from the ``wattage`` key in the PSU specs.

        Args:
            psu: The selected PSU component.
            build: The full tower build, used to aggregate component TDPs.

        Returns:
            An error message string when PSU wattage is insufficient, otherwise
            ``None``.
        """
        psu_wattage = _get_float_spec(psu.specs.specs, "wattage")
        if psu_wattage is None:
            return None

        cpu_tdp = _get_float_spec(build.cpu.specs.specs, "tdp") or 0.0

        gpu_tdp = 0.0
        if build.gpu is not None:
            gpu_tdp = _get_float_spec(build.gpu.specs.specs, "tdp") or 0.0

        total_tdp = cpu_tdp + gpu_tdp
        if total_tdp == 0.0:
            # No TDP data available; skip rather than raising a false-positive.
            return None

        required_wattage = total_tdp * (1.0 + _PSU_HEADROOM)
        if psu_wattage < required_wattage:
            return (
                f"PSU wattage {psu_wattage:.0f}W is insufficient; "
                f"requires at least {required_wattage:.0f}W "
                f"(total TDP {total_tdp:.0f}W + {_PSU_HEADROOM_PCT}% headroom)."
            )
        return None

    def validate_form_factor(
        self, case: ComponentSelection, motherboard: ComponentSelection
    ) -> str | None:
        """Check that the case form factor accommodates the motherboard.

        Downsizing is always allowed: an mATX board fits in an ATX case, and
        an ITX board fits in both mATX and ATX cases.  A larger motherboard
        cannot fit in a smaller case.

        Form factor rank (higher = physically smaller):
        - ``ATX`` → 0  (largest)
        - ``MATX`` / ``MICRO-ATX`` → 1
        - ``ITX`` / ``MINI-ITX`` → 2  (smallest)

        Args:
            case: The selected case component.
            motherboard: The selected motherboard component.

        Returns:
            An error message string when the motherboard does not fit in the
            case, otherwise ``None``.
        """
        case_ff = str(case.specs.specs.get("form_factor", "")).upper()
        mb_ff = str(motherboard.specs.specs.get("form_factor", "")).upper()

        if not case_ff or not mb_ff:
            return None

        case_rank = _FORM_FACTOR_RANK.get(case_ff)
        mb_rank = _FORM_FACTOR_RANK.get(mb_ff)

        if case_rank is None or mb_rank is None:
            # Unknown form factor string; skip rather than raising a false-positive.
            logger.warning(
                "Unknown form factor encountered during validation: case=%s, motherboard=%s",
                case_ff,
                mb_ff,
            )
            return None

        # The motherboard must be the same size or smaller than the case.
        # A higher rank means a smaller form factor, so mb_rank must be >= case_rank.
        if mb_rank < case_rank:
            return (
                f"Motherboard form factor '{mb_ff}' does not fit in a '{case_ff}' case "
                f"(requires same or smaller form factor)."
            )
        return None

    def assert_valid(self, build: TowerBuild) -> None:
        """Validate all rules and raise if any compatibility check fails.

        Collects all rule violations in a single pass before raising, so the
        caller receives the complete list of issues at once.

        Args:
            build: The tower build to validate.

        Raises:
            CompatibilityError: When one or more compatibility rules fail.
                The error message contains all detected issues joined by ``'; '``.
        """
        errors = self.validate_build(build)
        if errors:
            details = "; ".join(errors)
            raise CompatibilityError(f"Build compatibility validation failed: {details}")
