"""Pydantic schemas for bundle API request/response contracts."""

import enum
from datetime import datetime

from pydantic import BaseModel, Field

from orchestrator.schemas.product import ProductDetail


class PeripheralCategory(enum.StrEnum):
    """Peripheral component categories for bundle creation.

    Attributes:
        KEYBOARD: Keyboard peripheral.
        MOUSE: Mouse peripheral.
        MONITOR: Monitor / display peripheral.
        SPEAKERS: Speakers / audio peripheral.
    """

    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    MONITOR = "monitor"
    SPEAKERS = "speakers"


class PeripheralSelection(BaseModel):
    """A peripheral component selected for inclusion in a bundle.

    Attributes:
        sku: Stock-keeping unit code of the selected peripheral.
        normalized_name: Normalised human-readable product name.
        category: Peripheral category enum value.
        price: Unit price at the time of selection.
        specs: Full product detail of the peripheral.
    """

    sku: str
    normalized_name: str
    category: PeripheralCategory
    price: float
    specs: ProductDetail


class BundleBuild(BaseModel):
    """A complete bundle definition combining a tower with peripherals.

    Attributes:
        tower_hash: SHA-256 hash identifying the associated tower build.
        tier: Build tier name (e.g. ``"Home"``, ``"Business"``, ``"Gaming"``).
        peripherals: List of selected peripheral components.
        bundle_id: SHA-256 hash uniquely identifying this bundle, computed
            after peripheral selection. Defaults to an empty string.
        total_peripheral_price: Sum of all selected peripheral prices.
            Defaults to ``0.0``.
    """

    tower_hash: str
    tier: str
    peripherals: list[PeripheralSelection]
    bundle_id: str = ""
    total_peripheral_price: float = 0.0


class BundleSummary(BaseModel):
    """Summary of a published bundle for list endpoints.

    Attributes:
        bundle_id: SHA-256 hash uniquely identifying the bundle.
        tower_hash: SHA-256 hash of the associated tower build.
        peripheral_skus: Mapping of peripheral role to SKU (and any extra data).
        ml_id: Optional external ML system identifier.
        created_at: Timestamp when the bundle was first published.
    """

    bundle_id: str
    tower_hash: str
    peripheral_skus: dict[str, object]
    ml_id: str | None
    created_at: datetime


class BundleDetail(BaseModel):
    """Detailed bundle info for single-bundle endpoints.

    Attributes:
        bundle_id: SHA-256 hash uniquely identifying the bundle.
        tower_hash: SHA-256 hash of the associated tower build.
        peripheral_skus: Mapping of peripheral role to SKU (and any extra data).
        ml_id: Optional external ML system identifier.
        created_at: Timestamp when the bundle was first published.
        updated_at: Timestamp of the most recent update.
    """

    bundle_id: str
    tower_hash: str
    peripheral_skus: dict[str, object]
    ml_id: str | None
    created_at: datetime
    updated_at: datetime


class BundleListResponse(BaseModel):
    """Paginated list of published bundles.

    Attributes:
        count: Total number of bundles matching the query.
        bundles: List of bundle summaries for the current page.
    """

    count: int
    bundles: list[BundleSummary] = Field(default_factory=list)
