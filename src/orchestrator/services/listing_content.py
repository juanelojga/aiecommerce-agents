"""Listing content generator for MercadoLibre product listings.

Generates titles (≤ 60 characters) and structured descriptions from
tower build and bundle data.  This module is pure logic with no external
dependencies, making it trivially testable and fully deterministic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# MercadoLibre title character limit.
_ML_TITLE_MAX_LENGTH: int = 60

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

# Standard footer appended to every listing description.
_DESCRIPTION_FOOTER: str = (
    "---\nArmado y testeado. Garantía incluida. Consulte por envíos y financiación."
)


class ListingContentGenerator:
    """Generates MercadoLibre listing titles and descriptions from build data.

    All methods are pure functions with no side effects, ensuring
    identical inputs always produce identical outputs.

    No external dependencies are required; all logic is string manipulation.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_title(
        self,
        build: dict[str, object],
        bundle: dict[str, object] | None = None,
    ) -> str:
        """Generate a listing title of at most 60 characters.

        For tower-only builds the format is::

            "PC {Tier} {CPU_short} {RAM_short} {GPU_short}"

        For bundles the ``"Kit PC"`` prefix is used instead::

            "Kit PC {Tier} {CPU_short} {RAM_short}"

        GPU is appended only when the build contains a GPU component and the
        resulting string does not exceed the 60-character limit.  The final
        result is truncated to 60 characters if the assembled parts are still
        too long.

        Args:
            build: Serialised ``TowerBuild`` dict from the Inventory Architect.
            bundle: Optional serialised ``BundleBuild`` dict.  When provided
                the title is formatted as a Kit listing.

        Returns:
            A title string of at most ``_ML_TITLE_MAX_LENGTH`` characters.
        """
        tier = str(build.get("tier", ""))

        cpu = build.get("cpu")
        cpu_short = self._extract_short_name(cpu) if isinstance(cpu, dict) else ""

        ram = build.get("ram")
        ram_short = self._extract_short_name(ram) if isinstance(ram, dict) else ""

        gpu = build.get("gpu")
        gpu_short = self._extract_short_name(gpu) if isinstance(gpu, dict) else ""

        prefix = "Kit PC" if bundle is not None else "PC"

        # Build title incrementally, adding GPU only when it fits.
        parts: list[str] = [prefix, tier]
        if cpu_short:
            parts.append(cpu_short)
        if ram_short:
            parts.append(ram_short)

        title = " ".join(parts)

        # Append GPU for tower (non-bundle) listings when it fits.
        if bundle is None and gpu_short:
            candidate = f"{title} {gpu_short}"
            if len(candidate) <= _ML_TITLE_MAX_LENGTH:
                title = candidate

        return title[:_ML_TITLE_MAX_LENGTH]

    def generate_description(
        self,
        build: dict[str, object],
        bundle: dict[str, object] | None = None,
    ) -> str:
        """Generate a structured listing description with component specs.

        The description contains:

        1. A component specifications section listing each present component.
        2. A peripherals section (only when ``bundle`` is provided and has
           peripheral entries).
        3. A standard footer with assembly and warranty information.

        Args:
            build: Serialised ``TowerBuild`` dict from the Inventory Architect.
            bundle: Optional serialised ``BundleBuild`` dict.  When provided a
                peripherals section is appended.

        Returns:
            A multi-line description string ready for MercadoLibre.
        """
        lines: list[str] = []

        # -- Component specifications section --
        lines.append("== Especificaciones del PC ==")
        for role in _COMPONENT_ROLES:
            component = build.get(role)
            if component and isinstance(component, dict):
                name = str(component.get("normalized_name", ""))
                if name:
                    lines.append(f"{role.upper()}: {name}")

        # -- Peripherals section (bundle only) --
        if bundle is not None:
            peripherals = bundle.get("peripherals")
            if peripherals and isinstance(peripherals, list):
                lines.append("")
                lines.append("== Periféricos incluidos ==")
                for peripheral in peripherals:
                    if not isinstance(peripheral, dict):
                        continue
                    p_name = str(peripheral.get("normalized_name", ""))
                    p_category = str(peripheral.get("category", ""))
                    if p_name:
                        if p_category:
                            lines.append(f"{p_category.capitalize()}: {p_name}")
                        else:
                            lines.append(p_name)

        # -- Standard footer --
        lines.append("")
        lines.append(_DESCRIPTION_FOOTER)

        return "\n".join(lines)

    def _extract_short_name(self, component: Mapping[str, object]) -> str:
        """Extract a short display name from a component dict.

        Drops the first token (typically the brand name) when the
        ``normalized_name`` contains three or more whitespace-separated
        tokens.  For names with fewer than three tokens the full name is
        returned unchanged.

        Args:
            component: Component dict containing a ``normalized_name`` key.

        Returns:
            A shortened version of the component's normalised name, or an
            empty string when ``normalized_name`` is absent or empty.

        Examples:
            ``{"normalized_name": "Intel Core i7-13700K"}``  → ``"Core i7-13700K"``
            ``{"normalized_name": "RTX 4080"}``              → ``"RTX 4080"``
        """
        name = str(component.get("normalized_name", ""))
        if not name:
            return ""
        tokens = name.split()
        # Drop the leading brand token when there are three or more tokens.
        if len(tokens) >= 3:
            return " ".join(tokens[1:])
        return name
