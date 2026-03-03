"""LangGraph state definitions.

The graph state is treated as immutable within nodes — each node returns
a new state update dict rather than mutating the object in place.
"""

from typing import Annotated

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class GraphState(BaseModel):
    """Shared state passed through LangGraph nodes.

    Attributes:
        messages: Conversation messages accumulated via the ``add_messages`` reducer.
        context: Arbitrary context data available to all nodes.
    """

    messages: Annotated[list[dict[str, str]], add_messages] = Field(default_factory=list)
    context: dict[str, object] = Field(default_factory=dict)
