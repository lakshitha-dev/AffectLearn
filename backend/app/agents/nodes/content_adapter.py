"""Content Adapter node (Story 4.4 pass-through stub; real logic in Story 5.2).

Exists so the graph compiles to its final Phase B topology. Story 5.2 replaces the
body with the vLLM content-generation call. No LLM calls in Story 4.4.
"""

from typing import Any

from app.agents.state import AgentState


async def content_adapter_node(state: AgentState) -> dict[str, Any]:
    return {}
