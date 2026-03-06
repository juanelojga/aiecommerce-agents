"""Tests for LangGraph GraphState extensions (Task 12, Phase 2, 3 & 4)."""

from orchestrator.graph.state import GraphState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_BUILD: dict[str, object] = {
    "tier": "Home",
    "bundle_hash": "abc123",
    "total_price": 599.99,
}

SAMPLE_BUNDLE: dict[str, object] = {
    "tower_hash": "abc123",
    "tier": "Home",
    "peripheral_skus": ["MOUSE-001", "KB-001"],
    "bundle_id": "bndl-xyz789",
    "total_peripheral_price": 149.99,
}

SAMPLE_ASSET: dict[str, object] = {
    "bundle_id": "bndl-xyz789",
    "tier": "Home",
    "asset_type": "product_description",
    "content": "Experience seamless home computing with this complete kit.",
    "asset_id": "asset-abc001",
}

SAMPLE_LISTING: dict[str, object] = {
    "bundle_id": "bndl-xyz789",
    "tier": "Home",
    "channel": "storefront",
    "listing_id": "lst-def002",
    "status": "published",
}

SAMPLE_INVENTORY_ITEM: dict[str, object] = {
    "id": 1,
    "sku": "CPU-001",
    "name": "Ryzen 5 5600X",
    "category": "cpu",
    "price": 199.99,
    "available_quantity": 10,
    "is_active": True,
}

SAMPLE_SPECS: dict[str, object] = {
    "id": 1,
    "sku": "CPU-001",
    "socket": "AM4",
    "tdp": 65,
}


# ---------------------------------------------------------------------------
# test_graph_state_defaults
# ---------------------------------------------------------------------------


def test_graph_state_defaults() -> None:
    """New fields must have correct defaults on a freshly initialised state.

    Verifies that all Phase 1 tower-assembly fields default to the expected
    empty/zero values so that nodes can initialise a clean run without
    providing explicit values.
    """
    state = GraphState()

    # Core (backward-compatible) fields
    assert state.messages == []
    assert state.context == {}

    # Phase 1 fields
    assert state.requested_tiers == []
    assert state.inventory == []
    assert state.component_specs == {}
    assert state.completed_builds == []
    assert state.current_tier == ""
    assert state.errors == []
    assert state.run_status == "pending"


# ---------------------------------------------------------------------------
# test_graph_state_with_builds
# ---------------------------------------------------------------------------


def test_graph_state_with_builds() -> None:
    """A state populated with build data must serialise correctly.

    Verifies that ``completed_builds``, ``inventory``, ``component_specs``,
    ``requested_tiers``, ``current_tier``, and ``run_status`` round-trip
    through ``model_dump`` without data loss.
    """
    state = GraphState(
        requested_tiers=["Home", "Gaming"],
        inventory=[SAMPLE_INVENTORY_ITEM],
        component_specs={"CPU-001": SAMPLE_SPECS},
        completed_builds=[SAMPLE_BUILD],
        current_tier="Home",
        errors=[],
        run_status="completed",
    )

    dumped = state.model_dump()

    assert dumped["requested_tiers"] == ["Home", "Gaming"]
    assert dumped["inventory"] == [SAMPLE_INVENTORY_ITEM]
    assert dumped["component_specs"] == {"CPU-001": SAMPLE_SPECS}
    assert dumped["completed_builds"] == [SAMPLE_BUILD]
    assert dumped["current_tier"] == "Home"
    assert dumped["errors"] == []
    assert dumped["run_status"] == "completed"


# ---------------------------------------------------------------------------
# test_graph_state_immutable_update
# ---------------------------------------------------------------------------


def test_graph_state_immutable_update() -> None:
    """Producing a state update dict must not mutate the original state.

    Nodes return a plain ``dict`` that LangGraph merges into the state.
    This test confirms that constructing such an update from a copy of the
    current state leaves the original object unchanged.
    """
    original = GraphState(
        requested_tiers=["Home"],
        run_status="running",
    )

    # Simulate a node returning a state-update dict
    update: dict[str, object] = {
        **original.model_dump(),
        "completed_builds": [SAMPLE_BUILD],
        "run_status": "completed",
    }

    # Apply update by constructing a new state
    new_state = GraphState(**update)

    # Original must be unchanged
    assert original.completed_builds == []
    assert original.run_status == "running"

    # New state reflects the update
    assert new_state.completed_builds == [SAMPLE_BUILD]
    assert new_state.run_status == "completed"


# ---------------------------------------------------------------------------
# test_graph_state_errors_accumulate
# ---------------------------------------------------------------------------


def test_graph_state_errors_accumulate() -> None:
    """Error messages must be stored in the errors list without data loss."""
    state = GraphState(
        errors=["Compatibility check failed for CPU", "PSU wattage insufficient"],
        run_status="failed",
    )

    assert len(state.errors) == 2
    assert "Compatibility check failed for CPU" in state.errors
    assert state.run_status == "failed"


# ---------------------------------------------------------------------------
# test_graph_state_backward_compatible
# ---------------------------------------------------------------------------


def test_graph_state_backward_compatible() -> None:
    """Existing messages and context fields must remain fully functional.

    Ensures that the Phase 1 extension does not break any code that only
    uses the original ``messages`` and ``context`` fields.
    """
    state = GraphState(
        messages=[{"role": "user", "content": "Build me a gaming PC"}],
        context={"session_id": "abc", "user_id": 42},
    )

    assert len(state.messages) == 1
    assert state.messages[0]["role"] == "user"
    assert state.context["session_id"] == "abc"

    # Phase 1 fields should still be at their defaults
    assert state.requested_tiers == []
    assert state.run_status == "pending"


# ---------------------------------------------------------------------------
# test_graph_state_bundle_defaults
# ---------------------------------------------------------------------------


def test_graph_state_bundle_defaults() -> None:
    """``completed_bundles`` must default to an empty list on a fresh state.

    Verifies that the Phase 2 field is correctly initialised without requiring
    an explicit value, so Bundle Creator nodes can safely append to it.
    """
    state = GraphState()

    assert state.completed_bundles == []


# ---------------------------------------------------------------------------
# test_graph_state_with_bundles
# ---------------------------------------------------------------------------


def test_graph_state_with_bundles() -> None:
    """A state populated with bundle data must serialise correctly.

    Verifies that ``completed_bundles`` round-trips through ``model_dump``
    without data loss, preserving all fields of each bundle dict.
    """
    state = GraphState(completed_bundles=[SAMPLE_BUNDLE])

    dumped = state.model_dump()

    assert dumped["completed_bundles"] == [SAMPLE_BUNDLE]
    assert dumped["completed_bundles"][0]["tower_hash"] == "abc123"
    assert dumped["completed_bundles"][0]["tier"] == "Home"
    assert dumped["completed_bundles"][0]["bundle_id"] == "bndl-xyz789"
    assert dumped["completed_bundles"][0]["total_peripheral_price"] == 149.99


# ---------------------------------------------------------------------------
# test_graph_state_bundle_backward_compatible
# ---------------------------------------------------------------------------


def test_graph_state_bundle_backward_compatible() -> None:
    """All Phase 1 fields must remain unchanged after adding Phase 2 fields.

    Ensures that introducing ``completed_bundles`` does not alter the defaults
    or behaviour of any existing field from Phase 1.
    """
    state = GraphState(
        requested_tiers=["Home", "Gaming"],
        inventory=[SAMPLE_INVENTORY_ITEM],
        component_specs={"CPU-001": SAMPLE_SPECS},
        completed_builds=[SAMPLE_BUILD],
        current_tier="Gaming",
        errors=["minor warning"],
        run_status="running",
    )

    # Phase 2 field defaults to empty when not provided
    assert state.completed_bundles == []

    # All Phase 1 fields are unchanged
    assert state.requested_tiers == ["Home", "Gaming"]
    assert state.inventory == [SAMPLE_INVENTORY_ITEM]
    assert state.component_specs == {"CPU-001": SAMPLE_SPECS}
    assert state.completed_builds == [SAMPLE_BUILD]
    assert state.current_tier == "Gaming"
    assert state.errors == ["minor warning"]
    assert state.run_status == "running"


# ---------------------------------------------------------------------------
# test_graph_state_creative_defaults
# ---------------------------------------------------------------------------


def test_graph_state_creative_defaults() -> None:
    """``completed_assets`` must default to an empty list on a fresh state.

    Verifies that the Phase 3 field is correctly initialised without requiring
    an explicit value, so Creative Asset Generation nodes can safely append to it.
    """
    state = GraphState()

    assert state.completed_assets == []


# ---------------------------------------------------------------------------
# test_graph_state_with_assets
# ---------------------------------------------------------------------------


def test_graph_state_with_assets() -> None:
    """A state populated with asset data must serialise correctly.

    Verifies that ``completed_assets`` round-trips through ``model_dump``
    without data loss, preserving all fields of each asset dict.
    """
    state = GraphState(completed_assets=[SAMPLE_ASSET])

    dumped = state.model_dump()

    assert dumped["completed_assets"] == [SAMPLE_ASSET]
    assert dumped["completed_assets"][0]["bundle_id"] == "bndl-xyz789"
    assert dumped["completed_assets"][0]["tier"] == "Home"
    assert dumped["completed_assets"][0]["asset_id"] == "asset-abc001"
    assert dumped["completed_assets"][0]["asset_type"] == "product_description"


# ---------------------------------------------------------------------------
# test_graph_state_creative_backward_compatible
# ---------------------------------------------------------------------------


def test_graph_state_creative_backward_compatible() -> None:
    """All Phase 1 & 2 fields must remain unchanged after adding Phase 3 fields.

    Ensures that introducing ``completed_assets`` does not alter the defaults
    or behaviour of any existing field from Phase 1 or Phase 2.
    """
    state = GraphState(
        requested_tiers=["Home", "Gaming"],
        inventory=[SAMPLE_INVENTORY_ITEM],
        component_specs={"CPU-001": SAMPLE_SPECS},
        completed_builds=[SAMPLE_BUILD],
        current_tier="Gaming",
        errors=["minor warning"],
        run_status="running",
        completed_bundles=[SAMPLE_BUNDLE],
    )

    # Phase 3 field defaults to empty when not provided
    assert state.completed_assets == []

    # All Phase 1 fields are unchanged
    assert state.requested_tiers == ["Home", "Gaming"]
    assert state.inventory == [SAMPLE_INVENTORY_ITEM]
    assert state.component_specs == {"CPU-001": SAMPLE_SPECS}
    assert state.completed_builds == [SAMPLE_BUILD]
    assert state.current_tier == "Gaming"
    assert state.errors == ["minor warning"]
    assert state.run_status == "running"

    # Phase 2 field is unchanged
    assert state.completed_bundles == [SAMPLE_BUNDLE]


# ---------------------------------------------------------------------------
# test_graph_state_publication_defaults
# ---------------------------------------------------------------------------


def test_graph_state_publication_defaults() -> None:
    """``published_listings`` must default to an empty list on a fresh state.

    Verifies that the Phase 4 field is correctly initialised without requiring
    an explicit value, so Channel Manager nodes can safely append to it.
    """
    state = GraphState()

    assert state.published_listings == []


# ---------------------------------------------------------------------------
# test_graph_state_with_publications
# ---------------------------------------------------------------------------


def test_graph_state_with_publications() -> None:
    """A state populated with publication data must serialise correctly.

    Verifies that ``published_listings`` round-trips through ``model_dump``
    without data loss, preserving all fields of each listing dict.
    """
    state = GraphState(published_listings=[SAMPLE_LISTING])

    dumped = state.model_dump()

    assert dumped["published_listings"] == [SAMPLE_LISTING]
    assert dumped["published_listings"][0]["bundle_id"] == "bndl-xyz789"
    assert dumped["published_listings"][0]["tier"] == "Home"
    assert dumped["published_listings"][0]["listing_id"] == "lst-def002"
    assert dumped["published_listings"][0]["status"] == "published"


# ---------------------------------------------------------------------------
# test_graph_state_publication_backward_compatible
# ---------------------------------------------------------------------------


def test_graph_state_publication_backward_compatible() -> None:
    """All Phase 1, 2, and 3 fields must remain unchanged after adding Phase 4 fields.

    Ensures that introducing ``published_listings`` does not alter the defaults
    or behaviour of any existing field from Phases 1, 2, or 3.
    """
    state = GraphState(
        requested_tiers=["Home", "Gaming"],
        inventory=[SAMPLE_INVENTORY_ITEM],
        component_specs={"CPU-001": SAMPLE_SPECS},
        completed_builds=[SAMPLE_BUILD],
        current_tier="Gaming",
        errors=["minor warning"],
        run_status="running",
        completed_bundles=[SAMPLE_BUNDLE],
        completed_assets=[SAMPLE_ASSET],
    )

    # Phase 4 field defaults to empty when not provided
    assert state.published_listings == []

    # All Phase 1 fields are unchanged
    assert state.requested_tiers == ["Home", "Gaming"]
    assert state.inventory == [SAMPLE_INVENTORY_ITEM]
    assert state.component_specs == {"CPU-001": SAMPLE_SPECS}
    assert state.completed_builds == [SAMPLE_BUILD]
    assert state.current_tier == "Gaming"
    assert state.errors == ["minor warning"]
    assert state.run_status == "running"

    # Phase 2 field is unchanged
    assert state.completed_bundles == [SAMPLE_BUNDLE]

    # Phase 3 field is unchanged
    assert state.completed_assets == [SAMPLE_ASSET]
