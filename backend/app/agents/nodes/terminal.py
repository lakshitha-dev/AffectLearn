"""Terminal pass-through nodes for the agent graph (Story 4.4).

`log_only` is the Phase A / control terminal before END (FR28): affect was detected
and will be logged by the WS handler / research pipeline, but no adaptation is
produced. `deliver` is the Phase B terminal stub (real delivery is Story 5.3).
Both return state unchanged.
"""

from typing import Any

from app.agents.state import AgentState


async def log_only_node(state: AgentState) -> dict[str, Any]:
    return {}


async def deliver_node(state: AgentState) -> dict[str, Any]:
    return {}
