"""Peripheral selection service for the Bundle Creator (Agent 2).

Implements deterministic, tier-aware peripheral selection from available inventory.
No LLM involvement — pure business logic (FR-2.1, FR-2.2).
"""

import logging

from orchestrator.core.exceptions import InventoryError
from orchestrator.schemas.bundle import PeripheralCategory, PeripheralSelection
from orchestrator.schemas.product import ProductDetail, ProductListItem
from orchestrator.services.peripheral_rules import TierPeripheralSpec, get_tier_spec

logger = logging.getLogger(__name__)


class PeripheralSelector:
    """Selects tier-appropriate peripherals from available inventory.

    Deterministic selection using price-based sorting and tier rules.
    No LLM involvement — pure business logic.
    """

    async def select_peripherals(
        self,
        tier: str,
        peripheral_inventory: dict[str, list[ProductListItem]],
        specs_cache: dict[int, ProductDetail],
    ) -> list[PeripheralSelection]:
        """Select peripherals matching the tier's requirements.

        For each required peripheral category defined by the tier spec, picks one
        item according to the tier's selection strategy:

        - ``"cheapest"`` (Home): Sort by price ascending, pick the lowest-priced item.
        - ``"balanced"`` (Business): Sort by price ascending, pick the median item.
        - ``"premium"`` (Gaming): Sort by price ascending and select the most expensive item;
          for categories with filter_tags (e.g. ≥144 Hz monitors), prefer tag-matching items
          first, falling back to all items when no match is found.

        Args:
            tier: Target tier (Home, Business, Gaming).
            peripheral_inventory: Available peripheral items grouped by category.
            specs_cache: Cached product specs keyed by product ID.

        Returns:
            List of selected peripherals.

        Raises:
            InventoryError: If a required peripheral category has no stock.
        """
        spec: TierPeripheralSpec = get_tier_spec(tier)
        selections: list[PeripheralSelection] = []

        for category in spec.required_categories:
            items = peripheral_inventory.get(category.value, [])

            # Apply tag-based pre-filtering when the tier spec defines filter tags
            # for this category (e.g. ≥144 Hz for Gaming monitors).
            required_tags = spec.filter_tags.get(category, [])
            if required_tags:
                tagged_items = _filter_by_tags(items, required_tags, specs_cache)
                # Only restrict to tagged items if at least one match exists;
                # otherwise fall through to the full list.
                if tagged_items:
                    logger.debug(
                        "Tier '%s' %s: filtered from %d to %d items by tags %s.",
                        tier,
                        category.value,
                        len(items),
                        len(tagged_items),
                        required_tags,
                    )
                    items = tagged_items

            if not items:
                raise InventoryError(
                    f"No {category.value} peripherals available for tier '{tier}'."
                )

            selected = _select_item_for_strategy(items, spec.selection_strategy)
            peripheral_category = PeripheralCategory(category.value)

            detail = specs_cache.get(selected.id)
            if detail is None:
                raise InventoryError(
                    f"No cached spec found for {category.value} product id={selected.id}."
                )

            selections.append(
                PeripheralSelection(
                    sku=selected.sku,
                    normalized_name=selected.normalized_name,
                    category=peripheral_category,
                    price=selected.price,
                    specs=detail,
                )
            )
            logger.debug(
                "Tier '%s' selected %s peripheral: %s (£%.2f).",
                tier,
                category.value,
                selected.sku,
                selected.price,
            )

        return selections


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _select_item_for_strategy(
    items: list[ProductListItem],
    strategy: str,
) -> ProductListItem:
    """Pick one item from *items* according to the selection strategy.

    Args:
        items: Non-empty list of available peripheral items for a category.
        strategy: One of ``"cheapest"``, ``"balanced"``, or ``"premium"``.

    Returns:
        The selected :class:`ProductListItem`.
    """
    sorted_items = sorted(items, key=lambda i: i.price)

    if strategy == "cheapest":
        return sorted_items[0]
    if strategy == "balanced":
        return sorted_items[len(sorted_items) // 2]
    # "premium": most expensive first
    return sorted_items[-1]


def _filter_by_tags(
    items: list[ProductListItem],
    tags: list[str],
    specs_cache: dict[int, ProductDetail],
) -> list[ProductListItem]:
    """Return the subset of *items* whose specs contain at least one required tag.

    Tags are matched case-insensitively against:

    - String values stored in the product's ``specs`` dictionary.
    - Items in any list value stored in the ``specs`` dictionary.
    - Keys of the ``specs`` dictionary.

    Args:
        items: Available inventory items to filter.
        tags: Required tag strings (e.g. ``["144hz", "high-refresh"]``).
        specs_cache: Cached product specs keyed by product ID.

    Returns:
        Items that match at least one of the required tags, or an empty list
        when no items match.
    """
    lower_tags = [t.lower() for t in tags]

    def _matches(item: ProductListItem) -> bool:
        detail = specs_cache.get(item.id)
        if detail is None:
            return False
        specs = detail.specs
        for key, value in specs.items():
            if any(tag in key.lower() for tag in lower_tags):
                return True
            if isinstance(value, str) and any(tag in value.lower() for tag in lower_tags):
                return True
            if isinstance(value, list):
                for entry in value:
                    if isinstance(entry, str) and any(tag in entry.lower() for tag in lower_tags):
                        return True
        return False

    return [item for item in items if _matches(item)]
