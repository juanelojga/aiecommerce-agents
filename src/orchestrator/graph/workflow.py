"""LangGraph workflow definition for the aiecommerce-agents orchestrator.

Defines the Phase 3 assembly graph:

    START → inventory_architect → (success) → bundle_creator → (success) → creative_director → END
                                → (failure) → END              → (failure) → END

The ``_route_after_assembly`` helper routes successful assembly (completed with
non-empty builds) to the Bundle Creator node for peripheral bundling, while
failures or empty builds terminate the graph immediately.

The ``_route_after_bundle`` helper routes successful bundling (completed with
non-empty bundles) to the Creative Director node for media asset generation,
while failures or empty bundles terminate the graph.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from orchestrator.graph.nodes.bundle_creator import bundle_creator_node
from orchestrator.graph.nodes.creative_director import creative_director_node
from orchestrator.graph.nodes.inventory_architect import inventory_architect_node
from orchestrator.graph.state import GraphState

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

# Node name constants — used both when registering nodes and in edge
# definitions so that any future rename only needs to be updated once.
_NODE_INVENTORY_ARCHITECT = "inventory_architect"
_NODE_BUNDLE_CREATOR = "bundle_creator"
_NODE_CREATIVE_DIRECTOR = "creative_director"


def build_assembly_graph() -> CompiledStateGraph:  # type: ignore[type-arg]  # LangGraph generic params are implicit
    """Build and compile the LangGraph assembly workflow.

    Phase 3 graph::

        START → inventory_architect → (success) → bundle_creator
                                    → (failure) → END

        bundle_creator → (success) → creative_director → END
                       → (failure) → END

    The graph uses conditional edges after ``inventory_architect`` and
    ``bundle_creator`` to route successful results to the next processing
    node, while failures or empty results terminate the graph.

    Returns:
        Compiled StateGraph ready for invocation.
    """
    graph = StateGraph(GraphState)

    # Register processing nodes.
    graph.add_node(_NODE_INVENTORY_ARCHITECT, inventory_architect_node)
    graph.add_node(_NODE_BUNDLE_CREATOR, bundle_creator_node)
    graph.add_node(_NODE_CREATIVE_DIRECTOR, creative_director_node)

    # Entry point: START flows directly into the Inventory Architect.
    graph.add_edge(START, _NODE_INVENTORY_ARCHITECT)

    # Conditional edge: route based on assembly result.
    graph.add_conditional_edges(
        _NODE_INVENTORY_ARCHITECT,
        _route_after_assembly,
        {_NODE_BUNDLE_CREATOR: _NODE_BUNDLE_CREATOR, END: END},
    )

    # Conditional edge: route based on bundle result.
    graph.add_conditional_edges(
        _NODE_BUNDLE_CREATOR,
        _route_after_bundle,
        {_NODE_CREATIVE_DIRECTOR: _NODE_CREATIVE_DIRECTOR, END: END},
    )

    # Creative Director always flows to END.
    graph.add_edge(_NODE_CREATIVE_DIRECTOR, END)

    compiled = graph.compile()
    logger.debug("Assembly graph compiled successfully.")
    return compiled


def _route_after_assembly(state: GraphState) -> str:
    """Conditional edge: route based on assembly result.

    Routes to ``bundle_creator`` on success (completed with non-empty builds),
    or ``END`` on failure or empty builds.

    Args:
        state: Current graph state after the Inventory Architect node has run.

    Returns:
        ``_NODE_BUNDLE_CREATOR`` on success, ``END`` on failure or empty builds.
    """
    logger.debug("Routing after assembly: run_status=%s", state.run_status)
    if state.run_status == "completed" and state.completed_builds:
        return _NODE_BUNDLE_CREATOR
    return str(END)


def _route_after_bundle(state: GraphState) -> str:
    """Conditional edge: route based on bundle result.

    Routes to ``creative_director`` on success (completed with non-empty
    bundles), or ``END`` on failure or empty bundles.

    Args:
        state: Current graph state after the Bundle Creator node has run.

    Returns:
        ``_NODE_CREATIVE_DIRECTOR`` on success, ``END`` on failure or empty
        bundles.
    """
    logger.debug("Routing after bundle: run_status=%s", state.run_status)
    if state.run_status == "completed" and state.completed_bundles:
        return _NODE_CREATIVE_DIRECTOR
    return str(END)
