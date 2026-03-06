"""LangGraph state definitions.

The graph state is treated as immutable within nodes — each node returns
a new state update dict rather than mutating the object in place.
"""

from typing import Annotated, Literal

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class GraphState(BaseModel):
    """Shared state passed through LangGraph nodes.

    Attributes:
        messages: Conversation messages accumulated via the ``add_messages`` reducer.
        context: Arbitrary context data available to all nodes.
        requested_tiers: Build tiers requested for the current run (e.g. ``["Home", "Gaming"]``).
        inventory: Raw inventory items fetched from the aiecommerce API.
        component_specs: Cached product specs keyed by SKU.
        completed_builds: Successfully assembled tower builds for the current run.
        current_tier: The tier currently being processed by the Inventory Architect.
        errors: Accumulated error messages from any node in the graph.
        run_status: Literal["pending", "running", "completed", "failed"] indicating the
            overall status of the current run.
        completed_bundles: Serialized ``BundleBuild`` dicts produced by the Bundle Creator node.
            Each dict contains the tower_hash, tier, peripheral selections, bundle_id hash,
            and total_peripheral_price.
        completed_assets: Serialized creative asset dicts produced by the Creative Asset
            Generation node. Each dict contains the asset metadata and generated content.
        published_listings: Serialized published listing dicts produced by the Channel
            Manager node. Each dict contains publication results for a channel listing.
    """

    # ── Core fields (backward-compatible) ────────────────────────────────────
    messages: Annotated[list[dict[str, str]], add_messages] = Field(default_factory=list)
    context: dict[str, object] = Field(default_factory=dict)

    # ── Phase 1: Tower Assembly ───────────────────────────────────────────────
    requested_tiers: list[str] = Field(default_factory=list)
    inventory: list[dict[str, object]] = Field(default_factory=list)
    component_specs: dict[str, dict[str, object]] = Field(default_factory=dict)
    completed_builds: list[dict[str, object]] = Field(default_factory=list)
    current_tier: str = ""
    errors: list[str] = Field(default_factory=list)
    # Valid values: "pending" | "running" | "completed" | "failed"
    run_status: Literal["pending", "running", "completed", "failed"] = "pending"

    # ── Phase 2: Bundle Creation ──────────────────────────────────────────────
    completed_bundles: list[dict[str, object]] = Field(default_factory=list)

    # ── Phase 3: Creative Asset Generation ───────────────────────────────────
    completed_assets: list[dict[str, object]] = Field(default_factory=list)

    # ── Phase 4: Publication ──────────────────────────────────────────────────
    published_listings: list[dict[str, object]] = Field(default_factory=list)
