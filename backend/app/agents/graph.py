"""LangGraph StateGraph for the 4-agent affect loop (Story 4.4).

Topology (architecture lines 166-174):

    [START] -> affect_detection -> learner_profiler -> should_adapt?
                                                       |- log_only -> [END]      (Phase A / control)
                                                       '- pedagogical -> content_adapter -> deliver -> [END]  (Phase B / adaptive)

The graph carries a single `AgentState` (no side channels). It is compiled once and
reused per 30-second cycle via `get_graph()` (mirrors the lazy-singleton pattern in
`services.model_inference.get_model`). No checkpointer is configured — invocation is
in-memory and the per-cycle state (including raw facial frames) is discarded after
`ainvoke`, satisfying the no-video-storage privacy rule (NFR10).

Downstream nodes (pedagogical / content_adapter / deliver) are pass-through stubs in
Story 4.4 so the graph compiles to its final shape; later stories swap their bodies
without touching this topology.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.edges import ROUTE_LOG_ONLY, ROUTE_PEDAGOGICAL, route_after_profiler
from app.agents.nodes.affect_detection import affect_detection_node
from app.agents.nodes.content_adapter import content_adapter_node
from app.agents.nodes.learner_profiler import learner_profiler_node
from app.agents.nodes.pedagogical import pedagogical_node
from app.agents.nodes.terminal import deliver_node, log_only_node
from app.agents.state import AgentState


def build_graph() -> StateGraph:
    """Wire the StateGraph to the architecture topology (uncompiled)."""
    g = StateGraph(AgentState)

    g.add_node("affect_detection", affect_detection_node)
    g.add_node("learner_profiler", learner_profiler_node)
    g.add_node("log_only", log_only_node)
    g.add_node("pedagogical", pedagogical_node)
    g.add_node("content_adapter", content_adapter_node)
    g.add_node("deliver", deliver_node)

    g.add_edge(START, "affect_detection")
    g.add_edge("affect_detection", "learner_profiler")
    g.add_conditional_edges(
        "learner_profiler",
        route_after_profiler,
        {ROUTE_LOG_ONLY: "log_only", ROUTE_PEDAGOGICAL: "pedagogical"},
    )
    g.add_edge("pedagogical", "content_adapter")
    g.add_edge("content_adapter", "deliver")
    g.add_edge("deliver", END)
    g.add_edge("log_only", END)
    return g


_COMPILED: Any | None = None


def get_graph() -> Any:
    """Return the process-wide compiled graph, compiling on first use."""
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = build_graph().compile()
    return _COMPILED
