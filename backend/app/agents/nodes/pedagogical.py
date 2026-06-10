"""Pedagogical Strategist node (Story 4.4 pass-through stub; real logic in Story 5.1).

Exists so the graph compiles to its final Phase B topology. Story 5.1 replaces the
body with the vLLM strategy call. No LLM calls in Story 4.4.
"""

from typing import Any

from app.agents.state import AgentState


async def pedagogical_node(state: AgentState) -> dict[str, Any]:
    return {}
