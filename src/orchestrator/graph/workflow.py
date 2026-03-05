"""LangGraph workflow definition for the aiecommerce-agents orchestrator.

Defines the Phase 1 assembly graph:

    START → inventory_architect → END

The ``_route_after_assembly`` helper provides a conditional-edge scaffold that
routes every outcome to ``END`` in Phase 1.  Future phases will extend this
routing to support additional nodes (e.g. listing agent, recommendation agent).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from orchestrator.graph.nodes.inventory_architect import inventory_architect_node
from orchestrator.graph.state import GraphState

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

# Node name constant — used both when registering the node and in edge
# definitions so that any future rename only needs to be updated once.
_NODE_INVENTORY_ARCHITECT = "inventory_architect"


def build_assembly_graph() -> CompiledStateGraph:  # type: ignore[type-arg]  # LangGraph generic params are implicit
    """Build and compile the LangGraph assembly workflow.

    Phase 1 graph: START → inventory_architect → END

    The graph uses a conditional edge after ``inventory_architect`` to provide
    a routing scaffold for Phase 2 extensions (e.g. branching on failure).
    In Phase 1, all routes lead to ``END``.

    Returns:
        Compiled StateGraph ready for invocation.
    """
    graph = StateGraph(GraphState)

    # Register the Inventory Architect as the sole processing node.
    graph.add_node(_NODE_INVENTORY_ARCHITECT, inventory_architect_node)

    # Entry point: START flows directly into the Inventory Architect.
    graph.add_edge(START, _NODE_INVENTORY_ARCHITECT)

    # Conditional edge: route based on assembly result.
    # Phase 1 always routes to END; future phases can add more destinations.
    graph.add_conditional_edges(
        _NODE_INVENTORY_ARCHITECT,
        _route_after_assembly,
        {END: END},
    )

    compiled = graph.compile()
    logger.debug("Assembly graph compiled successfully.")
    return compiled


def _route_after_assembly(state: GraphState) -> str:
    """Conditional edge: route based on assembly result.

    In Phase 1 both success and failure outcomes route to ``END``.
    Future phases can inspect ``state.run_status`` to branch into additional
    processing nodes (e.g. a fallback or notification node).

    Args:
        state: Current graph state after the Inventory Architect node has run.

    Returns:
        ``END`` constant for both success and failure outcomes in Phase 1.
    """
    # Phase 1 scaffold — all outcomes terminate the graph.
    # Phase 2 extension point: check state.run_status == "failed" to branch.
    logger.debug("Routing after assembly: run_status=%s", state.run_status)
    return END
