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

import time
from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.edges import ROUTE_LOG_ONLY, ROUTE_PEDAGOGICAL, route_after_profiler
from app.agents.nodes.affect_detection import affect_detection_node
from app.agents.nodes.content_adapter import content_adapter_node
from app.agents.nodes.learner_profiler import learner_profiler_node
from app.agents.nodes.pedagogical import pedagogical_node
from app.agents.nodes.terminal import deliver_node, log_only_node
from app.agents.state import AgentState
from app.services.trace import emit_trace

# Nodes whose bodies are pass-through stubs today (Story 5.x). Surfaced on the dashboard
# so the flow diagram can mark them rather than implying real work happens.
# `pedagogical` became active in Story 5.1 (real vLLM strategy call).
STUB_NODES: tuple[str, ...] = ("content_adapter", "deliver")

# State keys whose values are safe + useful to echo into a node_completed trace.
_TRACE_OUTPUT_KEYS: tuple[str, ...] = (
    "affect_state",
    "affect_source",
    "detection_mode",
    "affect_confidence",
    "empty_cycle",
    "should_adapt",
    "engagement_level",
    "engagement_label",
)


def instrument(
    name: str, fn: Callable[[AgentState], Awaitable[dict[str, Any]]]
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    """Wrap a graph node to emit node_started / node_completed / node_error traces.

    Traces are live-only (monitor bus); the wrapped node's behaviour is unchanged and
    exceptions propagate so the WS handler's graceful degradation (NFR22) still applies.
    """
    node_kind = "stub" if name in STUB_NODES else "active"

    async def wrapped(state: AgentState) -> dict[str, Any]:
        ctx = {
            "learner_id": state.get("learner_id"),
            "session_id": state.get("session_id"),
            "cycle_number": state.get("cycle_number"),
        }
        emit_trace("node_started", node=name, node_kind=node_kind, **ctx)
        t0 = time.perf_counter()
        try:
            update = await fn(state) or {}
        except Exception as exc:
            emit_trace(
                "node_error",
                node=name,
                node_kind=node_kind,
                error=str(exc),
                duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                **ctx,
            )
            raise
        outputs = {k: update[k] for k in _TRACE_OUTPUT_KEYS if k in update}
        for k in ("strategy", "adaptation_content"):
            if k in update and update[k]:
                val = update[k]
                if k == "strategy" and isinstance(val, dict):
                    # Surface key decision fields for active pedagogical node
                    outputs[k] = {
                        "action_type": val.get("action_type"),
                        "urgency": val.get("urgency"),
                        "fallback": val.get("fallback"),
                    }
                else:
                    outputs[k] = True  # presence only (stub outputs)
        emit_trace(
            "node_completed",
            node=name,
            node_kind=node_kind,
            duration_ms=round((time.perf_counter() - t0) * 1000, 2),
            output_keys=list(update.keys()),
            outputs=outputs,
            **ctx,
        )
        return update

    return wrapped


def _route_reason(state: AgentState, chosen: str) -> str:
    if chosen == ROUTE_PEDAGOGICAL:
        return "phase_b + adaptive → pedagogical (adaptive branch)"
    return f"{state.get('phase')}/{state.get('group')} → log_only (no adaptation)"


def instrument_router(fn: Callable[[AgentState], str]) -> Callable[[AgentState], str]:
    """Wrap the conditional router to emit a route_decision trace (the 'why')."""

    def wrapped(state: AgentState) -> str:
        chosen = fn(state)
        emit_trace(
            "route_decision",
            router="route_after_profiler",
            chosen=chosen,
            phase=state.get("phase"),
            group=state.get("group"),
            should_adapt=bool(state.get("should_adapt")),
            reason=_route_reason(state, chosen),
            learner_id=state.get("learner_id"),
            session_id=state.get("session_id"),
            cycle_number=state.get("cycle_number"),
        )
        return chosen

    return wrapped


def build_graph() -> StateGraph:
    """Wire the StateGraph to the architecture topology (uncompiled).

    Every node is wrapped with `instrument` and the conditional router with
    `instrument_router` so the observability dashboard receives per-node execution
    spans and the routing decision for each cycle.
    """
    g = StateGraph(AgentState)

    g.add_node("affect_detection", instrument("affect_detection", affect_detection_node))
    g.add_node("learner_profiler", instrument("learner_profiler", learner_profiler_node))
    g.add_node("log_only", instrument("log_only", log_only_node))
    g.add_node("pedagogical", instrument("pedagogical", pedagogical_node))
    g.add_node("content_adapter", instrument("content_adapter", content_adapter_node))
    g.add_node("deliver", instrument("deliver", deliver_node))

    g.add_edge(START, "affect_detection")
    g.add_edge("affect_detection", "learner_profiler")
    g.add_conditional_edges(
        "learner_profiler",
        instrument_router(route_after_profiler),
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
