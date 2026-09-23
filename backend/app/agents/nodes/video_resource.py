"""Video sub-agent node: the Pedagogical agent's delegate for finding one explanation video.

The Pedagogical Strategist (Agent 3) orchestrates. When it decides that text help has not landed
it chooses `show_video` and writes a brief (`strategy.video_brief = {concept, query}`) grounded in
what the learner got wrong. This node carries out that delegation: it hands the brief to the Video
Resource Agent (`services/video_resource_agent.py`), which searches YouTube and picks one video,
and reports the result back into state for `deliver`.

PARALLEL, NOT SEQUENTIAL

The graph fans out from `pedagogical` to BOTH this node and `content_adapter`, and joins at
`deliver`. The strategist therefore never waits on YouTube, and the Content Adapter writes the
card's introduction while the video is being found. On every other action this node returns `{}`
immediately, so the fan-out costs nothing on the ordinary path.

BOUNDED, AND NEVER EMPTY-HANDED

The node gets a short budget. If the sub-agent finishes, the card arrives with the video. If not,
the card arrives with `pending=True` and the same brief, and the client completes the lookup
through the on-demand endpoint -- so a slow search delays the video, never the card. Never raises.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from app.agents.state import AgentState
from app.services import video_resource_agent
from app.services.research_logger import content_coords
from app.services.research_logger import emit as emit_research_event

logger = structlog.get_logger(__name__)

#: How long the delegation may take inside a cycle. With a brief the sub-agent makes one search
#: and at most one model call, which normally fits; past this the client finishes the job.
SUBAGENT_TIMEOUT_S = 5.0

#: Fields the card may carry. Internals (cache source, the model's raw output) stay server-side.
_WIRE_FIELDS = ("kind", "url", "video_id", "title", "channel", "duration_s", "reason")


async def video_resource_node(state: AgentState) -> dict[str, Any]:
    strategy = state.get("strategy") or {}
    if strategy.get("action_type") != "show_video":
        return {}

    context = state.get("content_context") or {}
    brief = video_resource_agent.clean_brief(strategy.get("video_brief"))
    result = await video_resource_agent.find_video(
        context, brief=brief, timeout_s=SUBAGENT_TIMEOUT_S
    )

    if result.get("source") == "fallback":
        # Timed out or failed inside the cycle: hand the client the brief to finish with.
        query, concept = (
            (brief["query"], brief["concept"]) if brief
            else video_resource_agent.fallback_query(context)
        )
        video = {"pending": True, "concept": concept, "query": query}
    else:
        video = {k: result.get(k) for k in _WIRE_FIELDS if result.get(k) is not None}

    logger.info(
        "video_subagent_done",
        learner_id=state.get("learner_id"),
        pending=bool(video.get("pending")),
        kind=video.get("kind"),
        briefed=brief is not None,
    )
    await emit_research_event({
        "event_type": "video_resource_selected",
        "learner_id": state.get("learner_id"),
        "session_id": state.get("session_id"),
        "cycle_number": state.get("cycle_number") or 0,
        "timestamp": int(time.time() * 1000),
        "phase": state.get("phase"),
        "group": state.get("group"),
        **content_coords(context),
        "payload": {
            # Whether the strategist delegated a brief or the sub-agent had to write its own.
            "brief": brief,
            "pending": bool(video.get("pending")),
            "kind": result.get("kind"),
            "video_id": result.get("video_id"),
            "title": result.get("title"),
            "channel": result.get("channel"),
            "reason": result.get("reason"),
            "source": result.get("source"),
        },
    })
    return {"video_resource": video}
