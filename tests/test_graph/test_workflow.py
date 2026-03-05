"""Tests for the LangGraph assembly workflow (Task 14).

Covers:
- Graph compiles without error.
- End-to-end run with mocked node produces completed state.
- API/node failure propagates to failed state.
- Empty requested_tiers results in no builds.
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


# ---------------------------------------------------------------------------
# test_build_assembly_graph_compiles
# ---------------------------------------------------------------------------


def test_build_assembly_graph_compiles() -> None:
    """Graph must compile successfully without raising any exception.

    Verifies the Phase 1 graph topology:
      START → inventory_architect → END
    """
    compiled = build_assembly_graph()
    assert compiled is not None


# ---------------------------------------------------------------------------
# test_workflow_successful_run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_successful_run() -> None:
    """End-to-end run with a mocked node must produce a completed state with builds.

    The inventory_architect_node is patched to return a successful result so
    that no real API or database connections are required.
    """
    mock_result = _make_node_result(
        completed_builds=[SAMPLE_BUILD],
        errors=[],
        run_status="completed",
    )

    with patch(
        "orchestrator.graph.workflow.inventory_architect_node",
        new=AsyncMock(return_value=mock_result),
    ):
        compiled = build_assembly_graph()
        initial_state = GraphState(requested_tiers=["Home"])
        result = await compiled.ainvoke(initial_state)

    assert result["run_status"] == "completed"
    assert result["completed_builds"] == [SAMPLE_BUILD]
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
    """_route_after_assembly must return END for a successful (completed) state."""
    from langgraph.graph import END

    state = GraphState(run_status="completed", completed_builds=[SAMPLE_BUILD])
    route = _route_after_assembly(state)
    assert route == END


# ---------------------------------------------------------------------------
# test_route_after_assembly_failure
# ---------------------------------------------------------------------------


def test_route_after_assembly_failure() -> None:
    """_route_after_assembly must return END for a failed state (Phase 1 scaffold)."""
    from langgraph.graph import END

    state = GraphState(run_status="failed", errors=["Something went wrong"])
    route = _route_after_assembly(state)
    assert route == END
