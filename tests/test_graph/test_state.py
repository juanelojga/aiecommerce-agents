"""Tests for LangGraph GraphState extensions (Task 12)."""

from orchestrator.graph.state import GraphState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_BUILD: dict[str, object] = {
    "tier": "Home",
    "bundle_hash": "abc123",
    "total_price": 599.99,
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
