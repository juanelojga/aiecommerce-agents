"""Tests for the LangGraph assembly workflow (Phase 2 — Tower → Bundle pipeline).

Covers:
- Graph compiles without error (two nodes: inventory_architect, bundle_creator).
- Successful assembly routes to bundle_creator.
- Failed assembly routes directly to END.
- Completed assembly with empty builds routes to END.
- End-to-end run with mocked services produces both builds and bundles.
- Bundle node failure propagates to final state.
- Existing Phase 1 scenarios remain backward compatible.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.graph.state import GraphState
from orchestrator.graph.workflow import _route_after_assembly, build_assembly_graph

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_BUILD: dict[str, object] = {
    "tier": "Home",
    "bundle_hash": "deadbeef",
    "total_price": 599.99,
}

SAMPLE_BUNDLE: dict[str, object] = {
    "tower_hash": "deadbeef",
    "tier": "Home",
    "bundle_id": "abc123",
    "total_peripheral_price": 249.99,
}


def _make_node_result(
    completed_builds: list[dict[str, Any]],
    errors: list[str],
    run_status: str,
) -> dict[str, object]:
    """Return a minimal node-update dict matching what inventory_architect_node returns."""
    return {
        "completed_builds": completed_builds,
        "errors": errors,
        "run_status": run_status,
    }


def _make_bundle_result(
    completed_bundles: list[dict[str, Any]],
    errors: list[str],
    run_status: str,
) -> dict[str, object]:
    """Return a minimal node-update dict matching what bundle_creator_node returns."""
    return {
        "completed_bundles": completed_bundles,
        "errors": errors,
        "run_status": run_status,
    }


# ---------------------------------------------------------------------------
# test_build_assembly_graph_compiles
# ---------------------------------------------------------------------------


def test_build_assembly_graph_compiles() -> None:
    """Graph must compile successfully without raising any exception.

    Verifies the Phase 2 graph topology:
      START → inventory_architect → (success) → bundle_creator → END
                                  → (failure) → END
    """
    compiled = build_assembly_graph()
    assert compiled is not None


# ---------------------------------------------------------------------------
# test_workflow_successful_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_successful_run() -> None:
    """End-to-end run with a mocked node must produce a completed state with builds.

    The inventory_architect_node is patched to return a successful result,
    and the bundle_creator_node is patched to return bundles, so that no
    real API or database connections are required.
    """
    mock_architect_result = _make_node_result(
        completed_builds=[SAMPLE_BUILD],
        errors=[],
        run_status="completed",
    )
    mock_bundle_result = _make_bundle_result(
        completed_bundles=[SAMPLE_BUNDLE],
        errors=[],
        run_status="completed",
    )

    with (
        patch(
            "orchestrator.graph.workflow.inventory_architect_node",
            new=AsyncMock(return_value=mock_architect_result),
        ),
        patch(
            "orchestrator.graph.workflow.bundle_creator_node",
            new=AsyncMock(return_value=mock_bundle_result),
        ),
    ):
        compiled = build_assembly_graph()
        initial_state = GraphState(requested_tiers=["Home"])
        result = await compiled.ainvoke(initial_state)

    assert result["run_status"] == "completed"
    assert result["completed_builds"] == [SAMPLE_BUILD]
    assert result["completed_bundles"] == [SAMPLE_BUNDLE]
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# test_workflow_failed_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_failed_run() -> None:
    """A node-level failure must propagate to a failed run_status in the final state.

    Simulates an API error scenario where the Inventory Architect cannot fetch
    inventory, returning errors and a failed run_status.
    """
    error_msg = "Failed to fetch cpu inventory: connection refused"
    mock_result = _make_node_result(
        completed_builds=[],
        errors=[error_msg],
        run_status="failed",
    )

    with patch(
        "orchestrator.graph.workflow.inventory_architect_node",
        new=AsyncMock(return_value=mock_result),
    ):
        compiled = build_assembly_graph()
        initial_state = GraphState(requested_tiers=["Gaming"])
        result = await compiled.ainvoke(initial_state)

    assert result["run_status"] == "failed"
    assert result["completed_builds"] == []
    assert len(result["errors"]) == 1
    assert error_msg in result["errors"]


# ---------------------------------------------------------------------------
# test_workflow_empty_tiers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_empty_tiers() -> None:
    """Empty requested_tiers must result in no builds and a completed status.

    The inventory_architect_node short-circuits when no tiers are requested.
    """
    mock_result = _make_node_result(
        completed_builds=[],
        errors=[],
        run_status="completed",
    )

    with patch(
        "orchestrator.graph.workflow.inventory_architect_node",
        new=AsyncMock(return_value=mock_result),
    ):
        compiled = build_assembly_graph()
        initial_state = GraphState(requested_tiers=[])
        result = await compiled.ainvoke(initial_state)

    assert result["run_status"] == "completed"
    assert result["completed_builds"] == []
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# test_route_after_assembly_success
# ---------------------------------------------------------------------------


def test_route_after_assembly_success() -> None:
    """_route_after_assembly must return bundle_creator for a successful state."""
    state = GraphState(run_status="completed", completed_builds=[SAMPLE_BUILD])
    route = _route_after_assembly(state)
    assert route == "bundle_creator"


# ---------------------------------------------------------------------------
# test_route_after_assembly_failure
# ---------------------------------------------------------------------------


def test_route_after_assembly_failure() -> None:
    """_route_after_assembly must return END for a failed state."""
    from langgraph.graph import END

    state = GraphState(run_status="failed", errors=["Something went wrong"])
    route = _route_after_assembly(state)
    assert route == END


# ---------------------------------------------------------------------------
# test_workflow_routes_to_bundle_on_success
# ---------------------------------------------------------------------------


def test_workflow_routes_to_bundle_on_success() -> None:
    """Successful assembly (completed + non-empty builds) must route to bundle_creator."""
    state = GraphState(run_status="completed", completed_builds=[SAMPLE_BUILD])
    route = _route_after_assembly(state)
    assert route == "bundle_creator"


# ---------------------------------------------------------------------------
# test_workflow_routes_to_end_on_failure
# ---------------------------------------------------------------------------


def test_workflow_routes_to_end_on_failure() -> None:
    """Failed assembly must route directly to END."""
    from langgraph.graph import END

    state = GraphState(run_status="failed", errors=["Assembly failed"])
    route = _route_after_assembly(state)
    assert route == END


# ---------------------------------------------------------------------------
# test_workflow_routes_to_end_on_empty_builds
# ---------------------------------------------------------------------------


def test_workflow_routes_to_end_on_empty_builds() -> None:
    """Completed assembly with empty builds must route to END (skip bundling)."""
    from langgraph.graph import END

    state = GraphState(run_status="completed", completed_builds=[])
    route = _route_after_assembly(state)
    assert route == END


# ---------------------------------------------------------------------------
# test_workflow_end_to_end_with_bundle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_end_to_end_with_bundle() -> None:
    """Full pipeline must produce both builds and bundles when assembly succeeds.

    Both inventory_architect_node and bundle_creator_node are mocked to return
    successful results.
    """
    mock_architect_result = _make_node_result(
        completed_builds=[SAMPLE_BUILD],
        errors=[],
        run_status="completed",
    )
    mock_bundle_result = _make_bundle_result(
        completed_bundles=[SAMPLE_BUNDLE],
        errors=[],
        run_status="completed",
    )

    with (
        patch(
            "orchestrator.graph.workflow.inventory_architect_node",
            new=AsyncMock(return_value=mock_architect_result),
        ),
        patch(
            "orchestrator.graph.workflow.bundle_creator_node",
            new=AsyncMock(return_value=mock_bundle_result),
        ),
    ):
        compiled = build_assembly_graph()
        initial_state = GraphState(requested_tiers=["Home"])
        result = await compiled.ainvoke(initial_state)

    assert result["run_status"] == "completed"
    assert result["completed_builds"] == [SAMPLE_BUILD]
    assert result["completed_bundles"] == [SAMPLE_BUNDLE]
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# test_workflow_bundle_failure_propagates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_bundle_failure_propagates() -> None:
    """Bundle node failure must propagate to the final state.

    Assembly succeeds (routes to bundle_creator), but the bundle_creator_node
    returns a failed status. The final state must reflect the failure.
    """
    mock_architect_result = _make_node_result(
        completed_builds=[SAMPLE_BUILD],
        errors=[],
        run_status="completed",
    )
    mock_bundle_result = _make_bundle_result(
        completed_bundles=[],
        errors=["Peripheral inventory unavailable"],
        run_status="failed",
    )

    with (
        patch(
            "orchestrator.graph.workflow.inventory_architect_node",
            new=AsyncMock(return_value=mock_architect_result),
        ),
        patch(
            "orchestrator.graph.workflow.bundle_creator_node",
            new=AsyncMock(return_value=mock_bundle_result),
        ),
    ):
        compiled = build_assembly_graph()
        initial_state = GraphState(requested_tiers=["Home"])
        result = await compiled.ainvoke(initial_state)

    assert result["run_status"] == "failed"
    assert result["completed_bundles"] == []
    assert "Peripheral inventory unavailable" in result["errors"]
