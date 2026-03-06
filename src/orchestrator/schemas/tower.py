"""Pydantic schemas for tower API request/response contracts."""

from datetime import datetime

from pydantic import BaseModel, Field


class TowerSummary(BaseModel):
    """Summary of a published tower for list endpoints.

    Attributes:
        bundle_hash: SHA-256 hash uniquely identifying the build.
        category: Tower tier (Home, Business, or Gaming).
        status: Current publish status (Active or Paused).
        ml_id: Optional external ML system identifier.
        total_price: Total price of all components in the build.
        created_at: Timestamp when the tower was first published.
    """

    bundle_hash: str
    category: str
    status: str
    ml_id: str | None
    total_price: float
    created_at: datetime


class TowerDetail(BaseModel):
    """Detailed tower info including all component SKUs.

    Attributes:
        bundle_hash: SHA-256 hash uniquely identifying the build.
        category: Tower tier (Home, Business, or Gaming).
        status: Current publish status (Active or Paused).
        ml_id: Optional external ML system identifier.
        component_skus: Mapping of component role to SKU (and any extra data).
        total_price: Total price of all components in the build.
        created_at: Timestamp when the tower was first published.
        updated_at: Timestamp of the most recent update.
    """

    bundle_hash: str
    category: str
    status: str
    ml_id: str | None
    component_skus: dict[str, object]
    total_price: float
    created_at: datetime
    updated_at: datetime


class TowerListResponse(BaseModel):
    """Paginated list of published towers.

    Attributes:
        count: Total number of towers matching the query.
        towers: List of tower summaries for the current page.
    """

    count: int
    towers: list[TowerSummary]


class RunTriggerRequest(BaseModel):
    """Request body for manually triggering an assembly run.

    Attributes:
        tiers: List of tower tiers to assemble. Defaults to all three
            standard tiers: Home, Business, and Gaming.
    """

    tiers: list[str] = Field(default_factory=lambda: ["Home", "Business", "Gaming"])


class RunTriggerResponse(BaseModel):
    """Response from a manual assembly run trigger.

    Attributes:
        status: High-level outcome of the run (e.g. ``"completed"``).
        towers_created: Number of new towers successfully stored.
        tower_hashes: SHA-256 hashes of all newly created towers.
        bundles_created: Number of new bundles successfully created.
        assets_generated: Total number of creative assets produced during the run.
        errors: List of error messages encountered during the run.
    """

    status: str
    towers_created: int
    tower_hashes: list[str]
    bundles_created: int = 0
    assets_generated: int = 0
    errors: list[str] = Field(default_factory=list)
