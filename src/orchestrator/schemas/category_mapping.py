"""Mapping between internal component categories and aiecommerce API category strings.

The external aiecommerce API uses Spanish-language category names
(e.g. ``"PROCESADORES"``, ``"MOTHER BOARDS"``) that differ from the
internal ``ComponentCategory`` enum values (``"cpu"``, ``"motherboard"``).

This module provides a single-responsibility translation layer so the
rest of the codebase can work with clean, English-only enum values
while the API client sends/receives the correct external strings.
"""

from orchestrator.schemas.product import ComponentCategory

# ---------------------------------------------------------------------------
# Internal → API mapping
# ---------------------------------------------------------------------------

COMPONENT_TO_API: dict[ComponentCategory, str] = {
    ComponentCategory.CPU: "PROCESADORES",
    ComponentCategory.MOTHERBOARD: "MOTHER BOARDS",
    ComponentCategory.RAM: "MEMORIA RAM",
    ComponentCategory.GPU: "TARJETA DE VIDEO",
    ComponentCategory.SSD: "UNIDADES DE ESTADO SOLIDO Y DISCOS DUROS",
    ComponentCategory.PSU: "FUENTES DE PODER",
    ComponentCategory.CASE: "CASE",
    ComponentCategory.FAN: "ACCESORIOS",
    ComponentCategory.KEYBOARD: "TECLADOS",
    ComponentCategory.MOUSE: "MOUSE",
    ComponentCategory.MONITOR: "MONITORES Y TELEVISORES",
    ComponentCategory.SPEAKERS: "PARLANTES",
}

# ---------------------------------------------------------------------------
# API → Internal mapping (reverse look-up)
# ---------------------------------------------------------------------------

API_TO_COMPONENT: dict[str, ComponentCategory] = {v: k for k, v in COMPONENT_TO_API.items()}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def to_api_category(category: ComponentCategory) -> str:
    """Translate an internal ``ComponentCategory`` to the aiecommerce API string.

    Args:
        category: Internal component category enum member.

    Returns:
        The corresponding aiecommerce API category string.

    Raises:
        ValueError: If the category has no known API mapping.
    """
    try:
        return COMPONENT_TO_API[category]
    except KeyError:
        raise ValueError(
            f"No API mapping for category '{category}'. "
            f"Known categories: {', '.join(c.value for c in COMPONENT_TO_API)}"
        ) from None


def from_api_category(api_category: str) -> ComponentCategory:
    """Translate an aiecommerce API category string to a ``ComponentCategory``.

    The look-up is case-insensitive: the incoming string is normalized to
    upper-case before matching against the API category keys.

    Args:
        api_category: Category string as returned by the aiecommerce API.

    Returns:
        The corresponding ``ComponentCategory`` enum member.

    Raises:
        ValueError: If the API string has no known internal mapping.
    """
    normalized = api_category.strip().upper()
    result = API_TO_COMPONENT.get(normalized)
    if result is not None:
        return result

    raise ValueError(
        f"Unknown API category '{api_category}'. "
        f"Known API categories: {', '.join(API_TO_COMPONENT)}"
    ) from None
