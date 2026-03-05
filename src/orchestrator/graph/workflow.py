"""LangGraph workflow definition for the aiecommerce-agents orchestrator.

Defines the Phase 2 assembly graph:

    START → inventory_architect → (success) → bundle_creator → END
                                → (failure) → END

The ``_route_after_assembly`` helper routes successful assembly (completed with
non-empty builds) to the Bundle Creator node for peripheral bundling, while
failures or empty builds terminate the graph immediately.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from orchestrator.graph.nodes.bundle_creator import bundle_creator_node
from orchestrator.graph.nodes.inventory_architect import inventory_architect_node
from orchestrator.graph.state import GraphState

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

# Node name constants — used both when registering nodes and in edge
# definitions so that any future rename only needs to be updated once.
_NODE_INVENTORY_ARCHITECT = "inventory_architect"
_NODE_BUNDLE_CREATOR = "bundle_creator"


def build_assembly_graph() -> CompiledStateGraph:  # type: ignore[type-arg]  # LangGraph generic params are implicit
    """Build and compile the LangGraph assembly workflow.

    Phase 2 graph:

        START → inventory_architect → (success) → bundle_creator → END
                                    → (failure) → END

    The graph uses a conditional edge after ``inventory_architect`` to route
    successful assemblies (completed with non-empty builds) to the Bundle
    Creator, while failures or empty builds terminate the graph.

    Returns:
        Compiled StateGraph ready for invocation.
    """
    graph = StateGraph(GraphState)

    # Register processing nodes.
    graph.add_node(_NODE_INVENTORY_ARCHITECT, inventory_architect_node)
    graph.add_node(_NODE_BUNDLE_CREATOR, bundle_creator_node)

    # Entry point: START flows directly into the Inventory Architect.
    graph.add_edge(START, _NODE_INVENTORY_ARCHITECT)

    # Conditional edge: route based on assembly result.
    graph.add_conditional_edges(
        _NODE_INVENTORY_ARCHITECT,
        _route_after_assembly,
        {_NODE_BUNDLE_CREATOR: _NODE_BUNDLE_CREATOR, END: END},
    )

    # Bundle Creator always flows to END.
    graph.add_edge(_NODE_BUNDLE_CREATOR, END)

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
    return END
