"""Tests for the category mapping module.

Validates the bidirectional mapping between internal ``ComponentCategory``
enum values and the external aiecommerce API category strings.
"""

import pytest

from orchestrator.schemas.category_mapping import (
    API_TO_COMPONENT,
    COMPONENT_TO_API,
    from_api_category,
    to_api_category,
)
from orchestrator.schemas.product import ComponentCategory

# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------


def test_every_component_category_has_api_mapping() -> None:
    """Every ``ComponentCategory`` member must have an API mapping."""
    for member in ComponentCategory:
        assert member in COMPONENT_TO_API, f"Missing API mapping for {member!r}"


def test_reverse_mapping_has_same_length() -> None:
    """The reverse mapping must contain the same number of entries."""
    assert len(API_TO_COMPONENT) == len(COMPONENT_TO_API)


# ---------------------------------------------------------------------------
# to_api_category
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("internal", "expected_api"),
    [
        (ComponentCategory.CPU, "PROCESADORES"),
        (ComponentCategory.MOTHERBOARD, "MOTHER BOARDS"),
        (ComponentCategory.RAM, "MEMORIA RAM"),
        (ComponentCategory.GPU, "TARJETA DE VIDEO"),
        (ComponentCategory.SSD, "UNIDADES DE ESTADO SOLIDO Y DISCOS DUROS"),
        (ComponentCategory.PSU, "FUENTES DE PODER"),
        (ComponentCategory.CASE, "CASE"),
        (ComponentCategory.FAN, "ACCESORIOS"),
        (ComponentCategory.KEYBOARD, "TECLADOS"),
        (ComponentCategory.MOUSE, "MOUSE"),
        (ComponentCategory.MONITOR, "MONITORES Y TELEVISORES"),
        (ComponentCategory.SPEAKERS, "PARLANTES"),
    ],
)
def test_to_api_category(internal: ComponentCategory, expected_api: str) -> None:
    """``to_api_category`` returns the correct API string for each category."""
    assert to_api_category(internal) == expected_api


# ---------------------------------------------------------------------------
# from_api_category
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("api_string", "expected_internal"),
    [
        ("PROCESADORES", ComponentCategory.CPU),
        ("MOTHER BOARDS", ComponentCategory.MOTHERBOARD),
        ("MEMORIA RAM", ComponentCategory.RAM),
        ("TARJETA DE VIDEO", ComponentCategory.GPU),
        ("UNIDADES DE ESTADO SOLIDO Y DISCOS DUROS", ComponentCategory.SSD),
        ("FUENTES DE PODER", ComponentCategory.PSU),
        ("CASE", ComponentCategory.CASE),
        ("ACCESORIOS", ComponentCategory.FAN),
        ("TECLADOS", ComponentCategory.KEYBOARD),
        ("MOUSE", ComponentCategory.MOUSE),
        ("MONITORES Y TELEVISORES", ComponentCategory.MONITOR),
        ("PARLANTES", ComponentCategory.SPEAKERS),
    ],
)
def test_from_api_category(api_string: str, expected_internal: ComponentCategory) -> None:
    """``from_api_category`` returns the correct internal enum for each API string."""
    assert from_api_category(api_string) == expected_internal


def test_from_api_category_case_insensitive() -> None:
    """``from_api_category`` is case-insensitive."""
    assert from_api_category("procesadores") == ComponentCategory.CPU
    assert from_api_category("Mother Boards") == ComponentCategory.MOTHERBOARD
    assert from_api_category("memoria ram") == ComponentCategory.RAM


def test_from_api_category_strips_whitespace() -> None:
    """``from_api_category`` strips leading/trailing whitespace."""
    assert from_api_category("  PROCESADORES  ") == ComponentCategory.CPU


def test_from_api_category_unknown_raises() -> None:
    """``from_api_category`` raises ``ValueError`` for unknown API strings."""
    with pytest.raises(ValueError, match="Unknown API category"):
        from_api_category("UNKNOWN_CATEGORY")


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("category", list(ComponentCategory))
def test_round_trip(category: ComponentCategory) -> None:
    """Converting to API and back must return the original category."""
    api_string = to_api_category(category)
    assert from_api_category(api_string) == category
