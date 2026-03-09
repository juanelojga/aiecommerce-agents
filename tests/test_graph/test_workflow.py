"""Tests for the LangGraph assembly workflow.

Phase 4 — Tower → Bundle → Creative → Channel pipeline.

Covers:
- Graph compiles without error (four nodes: inventory_architect,
  bundle_creator, creative_director, channel_manager).
- Successful assembly routes to bundle_creator.
- Failed assembly routes directly to END.
- Completed assembly with empty builds routes to END.
- Successful bundling routes to creative_director.
- Failed bundling routes directly to END.
- Completed bundling with empty bundles routes to END.
- Successful creative routes to channel_manager.
- End-to-end run with mocked services produces builds, bundles, assets, and listings.
- Bundle node failure propagates to final state.
- Assembly failure skips both bundle, creative, and channel nodes.
- Existing Phase 1, 2, & 3 scenarios remain backward compatible.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.graph.state import GraphState
from orchestrator.graph.workflow import (
    _NODE_BUNDLE_CREATOR,
    _NODE_CHANNEL_MANAGER,
    _NODE_CREATIVE_DIRECTOR,
    _route_after_assembly,
    _route_after_bundle,
    _route_after_creative,
    build_assembly_graph,
)

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

SAMPLE_ASSET: dict[str, object] = {
    "tower_hash": "deadbeef",
    "media_type": "image",
    "url": "https://example.com/image.png",
}

SAMPLE_LISTING: dict[str, object] = {
    "ml_id": "MLA123456789",
    "tier": "Home",
    "title": "PC Home",
    "price": 799.99,
    "status": "active",
    "permalink": "https://www.mercadolibre.com.ar/MLA123456789",
    "tower_hash": "deadbeef",
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


def _make_creative_result(
    completed_assets: list[dict[str, Any]],
    errors: list[str],
    run_status: str,
) -> dict[str, object]:
    """Return a minimal node-update dict matching what creative_director_node returns."""
    return {
        "completed_assets": completed_assets,
        "errors": errors,
        "run_status": run_status,
    }


def _make_channel_result(
    published_listings: list[dict[str, Any]],
    errors: list[str],
    run_status: str,
) -> dict[str, object]:
    """Return a minimal node-update dict matching what channel_manager_node returns."""
    return {
        "published_listings": published_listings,
        "errors": errors,
        "run_status": run_status,
    }


# ---------------------------------------------------------------------------
# test_build_assembly_graph_compiles
# ---------------------------------------------------------------------------


def test_build_assembly_graph_compiles() -> None:
    """Graph must compile successfully without raising any exception.

    Verifies the Phase 4 graph topology:
      START → inventory_architect → (success) → bundle_creator
                                  → (failure) → END

      bundle_creator → (success) → creative_director
                     → (failure) → END

      creative_director → (success) → channel_manager → END
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
    the bundle_creator_node is patched to return bundles, the
    creative_director_node is patched to return assets, and the
    channel_manager_node is patched to return listings, so that no real
    API or database connections are required.
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
    mock_creative_result = _make_creative_result(
        completed_assets=[SAMPLE_ASSET],
        errors=[],
        run_status="completed",
    )
    mock_channel_result = _make_channel_result(
        published_listings=[SAMPLE_LISTING],
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
        patch(
            "orchestrator.graph.workflow.creative_director_node",
            new=AsyncMock(return_value=mock_creative_result),
        ),
        patch(
            "orchestrator.graph.workflow.channel_manager_node",
            new=AsyncMock(return_value=mock_channel_result),
        ),
    ):
        compiled = build_assembly_graph()
        initial_state = GraphState(requested_tiers=["Home"])
        result = await compiled.ainvoke(initial_state)

    assert result["run_status"] == "completed"
    assert result["completed_builds"] == [SAMPLE_BUILD]
    assert result["completed_bundles"] == [SAMPLE_BUNDLE]
    assert result["completed_assets"] == [SAMPLE_ASSET]
    assert result["published_listings"] == [SAMPLE_LISTING]
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
    """_route_after_assembly must return the Bundle Creator node for a successful state."""
    state = GraphState(run_status="completed", completed_builds=[SAMPLE_BUILD])
    route = _route_after_assembly(state)
    assert route == _NODE_BUNDLE_CREATOR


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
    """Successful assembly (completed + non-empty builds) must route to the Bundle Creator."""
    state = GraphState(run_status="completed", completed_builds=[SAMPLE_BUILD])
    route = _route_after_assembly(state)
    assert route == _NODE_BUNDLE_CREATOR


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
    """Full pipeline must produce builds, bundles, assets, and listings when assembly succeeds.

    All four nodes (inventory_architect_node, bundle_creator_node,
    creative_director_node, and channel_manager_node) are mocked to
    return successful results.
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
    mock_creative_result = _make_creative_result(
        completed_assets=[SAMPLE_ASSET],
        errors=[],
        run_status="completed",
    )
    mock_channel_result = _make_channel_result(
        published_listings=[SAMPLE_LISTING],
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
        patch(
            "orchestrator.graph.workflow.creative_director_node",
            new=AsyncMock(return_value=mock_creative_result),
        ),
        patch(
            "orchestrator.graph.workflow.channel_manager_node",
            new=AsyncMock(return_value=mock_channel_result),
        ),
    ):
        compiled = build_assembly_graph()
        initial_state = GraphState(requested_tiers=["Home"])
        result = await compiled.ainvoke(initial_state)

    assert result["run_status"] == "completed"
    assert result["completed_builds"] == [SAMPLE_BUILD]
    assert result["completed_bundles"] == [SAMPLE_BUNDLE]
    assert result["completed_assets"] == [SAMPLE_ASSET]
    assert result["published_listings"] == [SAMPLE_LISTING]
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# test_workflow_bundle_failure_propagates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_bundle_failure_propagates() -> None:
    """Bundle node failure must propagate to the final state and skip creative/channel.

    Assembly succeeds (routes to bundle_creator), but the bundle_creator_node
    returns a failed status. The final state must reflect the failure and
    the creative_director_node and channel_manager_node must not be invoked.
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
    creative_mock = AsyncMock()
    channel_mock = AsyncMock()

    with (
        patch(
            "orchestrator.graph.workflow.inventory_architect_node",
            new=AsyncMock(return_value=mock_architect_result),
        ),
        patch(
            "orchestrator.graph.workflow.bundle_creator_node",
            new=AsyncMock(return_value=mock_bundle_result),
        ),
        patch(
            "orchestrator.graph.workflow.creative_director_node",
            new=creative_mock,
        ),
        patch(
            "orchestrator.graph.workflow.channel_manager_node",
            new=channel_mock,
        ),
    ):
        compiled = build_assembly_graph()
        initial_state = GraphState(requested_tiers=["Home"])
        result = await compiled.ainvoke(initial_state)

    assert result["run_status"] == "failed"
    assert result["completed_bundles"] == []
    assert "Peripheral inventory unavailable" in result["errors"]
    creative_mock.assert_not_called()
    channel_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 3: Creative Director routing & integration tests
# ---------------------------------------------------------------------------


def test_build_assembly_graph_compiles_phase3() -> None:
    """4-node graph must compile with all four processing nodes registered."""
    compiled = build_assembly_graph()
    assert compiled is not None
    # Verify all four nodes are present in the compiled graph.
    node_names = set(compiled.get_graph().nodes)
    assert "inventory_architect" in node_names
    assert "bundle_creator" in node_names
    assert "creative_director" in node_names
    assert "channel_manager" in node_names


# ---------------------------------------------------------------------------
# test_route_after_bundle_success
# ---------------------------------------------------------------------------


def test_route_after_bundle_success() -> None:
    """_route_after_bundle must return creative_director on success."""
    state = GraphState(
        run_status="completed",
        completed_builds=[SAMPLE_BUILD],
        completed_bundles=[SAMPLE_BUNDLE],
    )
    route = _route_after_bundle(state)
    assert route == _NODE_CREATIVE_DIRECTOR


# ---------------------------------------------------------------------------
# test_route_after_bundle_failure
# ---------------------------------------------------------------------------


def test_route_after_bundle_failure() -> None:
    """_route_after_bundle must return END for a failed state."""
    from langgraph.graph import END

    state = GraphState(
        run_status="failed",
        completed_builds=[SAMPLE_BUILD],
        errors=["Bundle creation failed"],
    )
    route = _route_after_bundle(state)
    assert route == END


# ---------------------------------------------------------------------------
# test_route_after_bundle_empty
# ---------------------------------------------------------------------------


def test_route_after_bundle_empty() -> None:
    """_route_after_bundle must return END when bundles list is empty."""
    from langgraph.graph import END

    state = GraphState(
        run_status="completed",
        completed_builds=[SAMPLE_BUILD],
        completed_bundles=[],
    )
    route = _route_after_bundle(state)
    assert route == END


# ---------------------------------------------------------------------------
# test_workflow_end_to_end_with_creative
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_end_to_end_with_creative() -> None:
    """Full 4-node pipeline must produce builds, bundles, assets, and listings."""
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
    mock_creative_result = _make_creative_result(
        completed_assets=[SAMPLE_ASSET],
        errors=[],
        run_status="completed",
    )
    mock_channel_result = _make_channel_result(
        published_listings=[SAMPLE_LISTING],
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
        patch(
            "orchestrator.graph.workflow.creative_director_node",
            new=AsyncMock(return_value=mock_creative_result),
        ),
        patch(
            "orchestrator.graph.workflow.channel_manager_node",
            new=AsyncMock(return_value=mock_channel_result),
        ),
    ):
        compiled = build_assembly_graph()
        initial_state = GraphState(requested_tiers=["Home"])
        result = await compiled.ainvoke(initial_state)

    assert result["run_status"] == "completed"
    assert result["completed_builds"] == [SAMPLE_BUILD]
    assert result["completed_bundles"] == [SAMPLE_BUNDLE]
    assert result["completed_assets"] == [SAMPLE_ASSET]
    assert result["published_listings"] == [SAMPLE_LISTING]
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# test_workflow_bundle_failure_skips_creative
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_bundle_failure_skips_creative() -> None:
    """Bundle fail must skip creative director and channel manager nodes.

    Assembly succeeds and routes to bundle_creator, but the bundle node fails.
    The creative_director_node and channel_manager_node must not be invoked.
    """
    mock_architect_result = _make_node_result(
        completed_builds=[SAMPLE_BUILD],
        errors=[],
        run_status="completed",
    )
    mock_bundle_result = _make_bundle_result(
        completed_bundles=[],
        errors=["Peripheral API down"],
        run_status="failed",
    )
    creative_mock = AsyncMock()
    channel_mock = AsyncMock()

    with (
        patch(
            "orchestrator.graph.workflow.inventory_architect_node",
            new=AsyncMock(return_value=mock_architect_result),
        ),
        patch(
            "orchestrator.graph.workflow.bundle_creator_node",
            new=AsyncMock(return_value=mock_bundle_result),
        ),
        patch(
            "orchestrator.graph.workflow.creative_director_node",
            new=creative_mock,
        ),
        patch(
            "orchestrator.graph.workflow.channel_manager_node",
            new=channel_mock,
        ),
    ):
        compiled = build_assembly_graph()
        initial_state = GraphState(requested_tiers=["Home"])
        result = await compiled.ainvoke(initial_state)

    assert result["run_status"] == "failed"
    assert result["completed_assets"] == []
    assert result["published_listings"] == []
    creative_mock.assert_not_called()
    channel_mock.assert_not_called()


# ---------------------------------------------------------------------------
# test_workflow_assembly_failure_skips_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_assembly_failure_skips_all() -> None:
    """Assembly fail must skip bundle, creative director, and channel manager nodes.

    The inventory_architect_node returns a failed status. Neither the
    bundle_creator_node, creative_director_node, nor channel_manager_node
    must be invoked.
    """
    mock_architect_result = _make_node_result(
        completed_builds=[],
        errors=["Inventory API unreachable"],
        run_status="failed",
    )
    bundle_mock = AsyncMock()
    creative_mock = AsyncMock()
    channel_mock = AsyncMock()

    with (
        patch(
            "orchestrator.graph.workflow.inventory_architect_node",
            new=AsyncMock(return_value=mock_architect_result),
        ),
        patch(
            "orchestrator.graph.workflow.bundle_creator_node",
            new=bundle_mock,
        ),
        patch(
            "orchestrator.graph.workflow.creative_director_node",
            new=creative_mock,
        ),
        patch(
            "orchestrator.graph.workflow.channel_manager_node",
            new=channel_mock,
        ),
    ):
        compiled = build_assembly_graph()
        initial_state = GraphState(requested_tiers=["Gaming"])
        result = await compiled.ainvoke(initial_state)

    assert result["run_status"] == "failed"
    assert result["completed_builds"] == []
    assert result["completed_bundles"] == []
    assert result["completed_assets"] == []
    assert result["published_listings"] == []
    bundle_mock.assert_not_called()
    creative_mock.assert_not_called()
    channel_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 4: Channel Manager routing tests
# ---------------------------------------------------------------------------


def test_route_after_creative_success() -> None:
    """_route_after_creative must return channel_manager on success."""
    state = GraphState(
        run_status="completed",
        completed_builds=[SAMPLE_BUILD],
        completed_bundles=[SAMPLE_BUNDLE],
        completed_assets=[SAMPLE_ASSET],
    )
    route = _route_after_creative(state)
    assert route == _NODE_CHANNEL_MANAGER


def test_route_after_creative_failure() -> None:
    """_route_after_creative must return END for a failed state."""
    from langgraph.graph import END

    state = GraphState(
        run_status="failed",
        completed_builds=[SAMPLE_BUILD],
        errors=["Creative generation failed"],
    )
    route = _route_after_creative(state)
    assert route == END


def test_route_after_creative_empty_builds() -> None:
    """_route_after_creative must return END when builds list is empty."""
    from langgraph.graph import END

    state = GraphState(
        run_status="completed",
        completed_builds=[],
    )
    route = _route_after_creative(state)
    assert route == END
