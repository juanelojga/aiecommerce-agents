"""Pydantic schemas for inventory API responses and tower build objects."""

import enum

from pydantic import BaseModel, Field


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
    """

    CPU = "cpu"
    MOTHERBOARD = "motherboard"
    RAM = "ram"
    GPU = "gpu"
    SSD = "ssd"
    PSU = "psu"
    CASE = "case"
    FAN = "fan"


class InventoryItem(BaseModel):
    """A single component from the aiecommerce inventory.

    Maps to the items returned by ``GET /api/v1/agent/inventory/``.

    Attributes:
        id: Unique numeric identifier of the item.
        sku: Stock-keeping unit code.
        name: Human-readable component name.
        category: Component category enum value.
        price: Unit price in the store's base currency.
        available_quantity: Number of units currently in stock.
        is_active: Whether the item is listed as active.
        last_bundled_date: ISO-8601 date string of the last time this item was
            included in a bundle, or ``None`` if never bundled.
    """

    id: int
    sku: str
    name: str
    category: ComponentCategory
    price: float
    available_quantity: int
    is_active: bool
    last_bundled_date: str | None = None


class ProductSpecs(BaseModel):
    """Deep technical specifications for a component.

    Maps to the response of ``GET /api/v1/agent/product/{id}/specs/``.

    Attributes:
        id: Unique numeric identifier matching the inventory item.
        sku: Stock-keeping unit code.
        socket: CPU/motherboard socket type (e.g. ``"AM5"``), if applicable.
        ddr_generation: RAM DDR generation string (e.g. ``"DDR5"``), if applicable.
        form_factor: Physical form factor (e.g. ``"ATX"``), if applicable.
        wattage: Rated wattage for PSUs, if applicable.
        tdp: Thermal design power in watts, if applicable.
        ssd_interface: SSD bus interface (e.g. ``"NVMe"``), if applicable.
        has_integrated_psu: Whether the case includes an integrated PSU.
        included_fans: Number of fans bundled with the component.
        ram_speed: RAM operating speed in MHz, if applicable.
        extra_specs: Additional vendor-specific key-value specifications.
    """

    id: int
    sku: str
    socket: str | None = None
    ddr_generation: str | None = None
    form_factor: str | None = None
    wattage: int | None = None
    tdp: int | None = None
    ssd_interface: str | None = None
    has_integrated_psu: bool = False
    included_fans: int = 0
    ram_speed: int | None = None
    extra_specs: dict[str, object] = Field(default_factory=dict)


class InventoryResponse(BaseModel):
    """Response envelope from the aiecommerce inventory endpoint.

    Attributes:
        count: Total number of items available (before pagination).
        results: List of inventory items in the current page.
    """

    count: int
    results: list[InventoryItem]


class ComponentSelection(BaseModel):
    """A component selected for inclusion in a tower build.

    Attributes:
        sku: Stock-keeping unit code of the selected component.
        name: Human-readable component name.
        category: Component category enum value.
        price: Unit price at the time of selection.
        specs: Full technical specifications of the component.
    """

    sku: str
    name: str
    category: ComponentCategory
    price: float
    specs: ProductSpecs


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
