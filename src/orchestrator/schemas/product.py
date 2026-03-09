"""Pydantic schemas for product API responses and tower build objects."""

import enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ComponentCategory(enum.StrEnum):
    """Enumeration of supported PC component categories.

    Attributes:
        CPU: Central processing unit.
        MOTHERBOARD: Motherboard / mainboard.
        RAM: Random-access memory module.
        GPU: Graphics processing unit.
        SSD: Solid-state drive.
        PSU: Power supply unit.
        CASE: PC chassis / case.
        FAN: Case or CPU cooling fan.
        KEYBOARD: Keyboard peripheral.
        MOUSE: Mouse peripheral.
        MONITOR: Monitor / display peripheral.
        SPEAKERS: Speakers / audio peripheral.
    """

    CPU = "cpu"
    MOTHERBOARD = "motherboard"
    RAM = "ram"
    GPU = "gpu"
    SSD = "ssd"
    PSU = "psu"
    CASE = "case"
    FAN = "fan"
    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    MONITOR = "monitor"
    SPEAKERS = "speakers"


def _coerce_category(value: object) -> object:
    """Coerce an API category string or internal value to a ``ComponentCategory``.

    If *value* is already a ``ComponentCategory`` it is returned as-is.
    If it is a string that matches an internal enum value (e.g. ``"cpu"``)
    it passes through unchanged for Pydantic to convert.  Otherwise the
    string is looked up in the API → internal reverse mapping.

    Args:
        value: Raw category value from incoming data.

    Returns:
        A value that Pydantic can convert to ``ComponentCategory``.
    """
    if isinstance(value, ComponentCategory):
        return value

    if isinstance(value, str):
        # Fast path: value already matches an internal enum value.
        try:
            return ComponentCategory(value)
        except ValueError:
            pass

        # Slow path: try the API → internal reverse mapping (lazy import
        # to avoid a circular import at module level).
        from orchestrator.schemas.category_mapping import from_api_category

        try:
            return from_api_category(value)
        except ValueError:
            pass

    # Fall through — let Pydantic raise its own validation error.
    return value


class ProductListItem(BaseModel):
    """A single product from the aiecommerce product list.

    Maps to items returned by ``GET /api/v1/products/``.

    Attributes:
        id: Unique numeric identifier of the product.
        code: Internal product code.
        sku: Stock-keeping unit code.
        normalized_name: Normalised human-readable product name.
        price: Unit price in the store's base currency.
        category: Component category enum value.
        last_bundled_date: ISO-8601 date string of the last time this product was
            included in a bundle, or ``None`` if never bundled.
        is_active: Whether the product is listed as active.
        total_available_stock: Computed total units currently in stock across
            all warehouses.
    """

    id: int
    code: str
    sku: str
    normalized_name: str
    price: float
    category: ComponentCategory
    last_bundled_date: str | None = None
    is_active: bool = True
    total_available_stock: int = 0

    @field_validator("category", mode="before")
    @classmethod
    def _normalise_category(cls, value: Any) -> Any:
        """Accept both internal enum values and external API category strings."""
        return _coerce_category(value)


class ProductDetail(BaseModel):
    """Full product detail from the aiecommerce API.

    Maps to the response of ``GET /api/v1/products/{id}/``.

    Attributes:
        id: Unique numeric identifier of the product.
        code: Internal product code.
        sku: Stock-keeping unit code.
        normalized_name: Normalised human-readable product name.
        model_name: Manufacturer model name, if available.
        description: Long-form product description.
        seo_title: SEO-optimised title for the product page.
        seo_description: SEO-optimised meta description.
        price: Unit price in the store's base currency.
        category: Component category enum value.
        gtin: Global Trade Item Number (EAN/UPC), if available.
        specs: Technical specifications as a JSON dictionary.
        image_url: Primary product image URL.
        image_urls: Nested list of product image objects from
            ``ProductImageSerializer``.
        total_available_stock: Computed total units currently in stock.
    """

    id: int
    code: str
    sku: str
    normalized_name: str
    model_name: str | None = None
    description: str | None = None
    seo_title: str | None = None
    seo_description: str | None = None
    price: float
    category: ComponentCategory
    gtin: str | None = None
    specs: dict[str, object] = Field(default_factory=dict)
    image_url: str | None = None
    image_urls: list[dict[str, object]] = Field(default_factory=list)
    total_available_stock: int = 0

    @field_validator("category", mode="before")
    @classmethod
    def _normalise_category(cls, value: Any) -> Any:
        """Accept both internal enum values and external API category strings."""
        return _coerce_category(value)


class ProductListResponse(BaseModel):
    """Paginated response envelope from the aiecommerce products endpoint.

    Matches the standard DRF paginated response shape.

    Attributes:
        count: Total number of products available (before pagination).
        next: URL for the next page, or ``None`` if on the last page.
        previous: URL for the previous page, or ``None`` if on the first page.
        results: List of product items in the current page.
    """

    count: int
    next: str | None = None
    previous: str | None = None
    results: list[ProductListItem]


class ComponentSelection(BaseModel):
    """A component selected for inclusion in a tower build.

    Attributes:
        sku: Stock-keeping unit code of the selected component.
        normalized_name: Normalised human-readable product name.
        category: Component category enum value.
        price: Unit price at the time of selection.
        specs: Full product detail of the component.
    """

    sku: str
    normalized_name: str
    category: ComponentCategory
    price: float
    specs: ProductDetail


class TowerBuild(BaseModel):
    """A complete, validated PC tower build ready for assembly.

    Attributes:
        tier: Build tier name (e.g. ``"Home"``, ``"Business"``, ``"Gaming"``).
        cpu: Selected CPU component.
        motherboard: Selected motherboard component.
        ram: Selected RAM component.
        gpu: Optional selected GPU component.
        ssd: Selected SSD component.
        psu: Selected PSU component.
        case: Selected case component.
        fans: List of selected fan components.
        bundle_hash: Unique hash identifying this build combination.
        total_price: Sum of all selected component prices.
    """

    tier: str
    cpu: ComponentSelection
    motherboard: ComponentSelection
    ram: ComponentSelection
    gpu: ComponentSelection | None = None
    ssd: ComponentSelection
    psu: ComponentSelection
    case: ComponentSelection
    fans: list[ComponentSelection] = Field(default_factory=list)
    bundle_hash: str = ""
    total_price: float = 0.0
