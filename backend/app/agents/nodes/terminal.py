"""Terminal nodes for the agent graph (Story 4.4; `deliver` made active in Story 5.3).

`log_only` is the Phase A / control terminal before END (FR28): affect was detected
and will be logged by the WS handler / research pipeline, but no adaptation is
produced — it returns state unchanged.

`deliver` is the Phase B terminal. As of Story 5.3 it is ACTIVE: it builds the
downstream WebSocket `adaptation` wire payload from `AgentState.adaptation_content`
(written by the Content Adapter, Story 5.2) and writes it back into the returned
partial state under `delivery_message`. It does NOT touch any socket — graph nodes
receive only `AgentState` (no side channels — architecture lines 574-598, 1217). The
WS handler (`app.api.routes.ws`) owns the live socket and performs the actual
`send_json` of `delivery_message` after `ainvoke` returns. This keeps the wire shape
computed/tested inside the graph while transport stays at the boundary (mirrors how
affect is computed in-graph but the research event is emitted by the handler).

`no_action` (or absent / empty / malformed `adaptation_content`) -> the node returns
`{}` (no `delivery_message`), so the handler sends nothing and the learner's
experience is uninterrupted (AC3). The node NEVER raises on malformed content
(NFR22 / architecture line 335).
"""

from __future__ import annotations

import time
from typing import Any

from app.agents.state import AgentState


async def log_only_node(state: AgentState) -> dict[str, Any]:
    return {}


def _build_delivery_message(adaptation_content: Any) -> dict[str, Any] | None:
    """Build the downstream `adaptation` wire payload, or None if nothing to deliver.

    Pure + total: handles a well-formed `{text, variant, metadata}`, a partial dict, and
    any malformed input (non-dict, missing keys) without raising. Resolves the wire
    `action` from `metadata.action_type` (falling back to `variant`); `no_action`,
    unknown, or empty actions yield None (no delivery).
    """
    if not isinstance(adaptation_content, dict) or not adaptation_content:
        return None

    metadata = adaptation_content.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    variant = adaptation_content.get("variant")
    # Prefer the strategist's action_type; fall back to the content variant.
    action = metadata.get("action_type") or variant

    if not action or action == "no_action":
        return None

    text = adaptation_content.get("text")
    return {
        "type": "adaptation",
        "action": action,
        "content": {"text": text, "variant": variant},
        "ts": int(time.time() * 1000),
    }


async def deliver_node(state: AgentState) -> dict[str, Any]:
    """Build the WS `adaptation` payload from `adaptation_content` (Story 5.3).

    Returns `{"delivery_message": {...}}` when there is something to deliver, or `{}`
    for `no_action` / absent / empty / malformed content. Never touches a socket (it
    has none) and never raises (NFR22).
    """
    message = _build_delivery_message(state.get("adaptation_content"))
    if message is None:
        return {}
    return {"delivery_message": message}
