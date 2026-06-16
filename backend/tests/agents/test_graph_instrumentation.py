"""Tests for the graph node/router instrumentation that feeds the dashboard."""

from app.agents.edges import ROUTE_LOG_ONLY, ROUTE_PEDAGOGICAL
from app.agents.graph import instrument, instrument_router
from app.agents.edges import route_after_profiler
from app.services.monitor_bus import monitor_bus


async def test_instrument_emits_started_and_completed_with_outputs():
    async def fake_node(state):
        return {"affect_state": "engaged", "affect_confidence": 0.81, "detection_mode": "behavioral_only"}

    wrapped = instrument("affect_detection", fake_node)
    out = await wrapped({"session_id": "sess-instr", "cycle_number": 3, "learner_id": "L"})

    assert out["affect_state"] == "engaged"  # wrapper returns the node's update unchanged
    evs = monitor_bus.recent(session_id="sess-instr")
    types = [e["event_type"] for e in evs]
    assert "node_started" in types and "node_completed" in types

    completed = next(e for e in evs if e["event_type"] == "node_completed")
    assert completed["node"] == "affect_detection"
    assert completed["node_kind"] == "active"
    assert completed["outputs"]["affect_state"] == "engaged"
    assert "duration_ms" in completed


async def test_instrument_emits_error_and_reraises():
    async def boom(state):
        raise RuntimeError("kaboom")

    wrapped = instrument("learner_profiler", boom)
    raised = False
    try:
        await wrapped({"session_id": "sess-err", "cycle_number": 1})
    except RuntimeError:
        raised = True
    assert raised  # exception propagates (preserves NFR22 degradation)

    errs = [e for e in monitor_bus.recent(session_id="sess-err") if e["event_type"] == "node_error"]
    assert errs and errs[0]["error"] == "kaboom"


async def test_no_nodes_are_stubs_after_5_3():
    from app.agents.graph import STUB_NODES

    # Story 5.3: `deliver` went active (builds the WS wire payload), so no node is a
    # stub. `pedagogical` (5.1) and `content_adapter` (5.2) were already active.
    assert STUB_NODES == ()


async def test_instrument_marks_deliver_active_and_surfaces_delivery():
    async def fake_deliver(state):
        return {"delivery_message": {"type": "adaptation", "action": "show_hint",
                                     "content": {"text": "hi", "variant": "show_hint"},
                                     "ts": 1}}

    wrapped = instrument("deliver", fake_deliver)
    await wrapped({"session_id": "sess-deliver", "cycle_number": 1, "learner_id": "L"})
    evs = monitor_bus.recent(session_id="sess-deliver")
    started = next(e for e in evs if e["event_type"] == "node_started")
    assert started["node_kind"] == "active"  # deliver is no longer a stub
    completed = next(e for e in evs if e["event_type"] == "node_completed")
    # Surfaces the delivery decision (queued + action), not presence-only.
    assert completed["outputs"]["delivery_message"] == {"queued": True, "action": "show_hint"}


def test_router_emits_decision_with_reason():
    wrapped = instrument_router(route_after_profiler)

    chosen = wrapped({"phase": "phase_a", "group": "control", "session_id": "sess-route", "cycle_number": 1})
    assert chosen == ROUTE_LOG_ONLY

    adaptive = wrapped({"phase": "phase_b", "group": "adaptive", "session_id": "sess-route2", "cycle_number": 1})
    assert adaptive == ROUTE_PEDAGOGICAL

    dec = next(e for e in monitor_bus.recent(session_id="sess-route") if e["event_type"] == "route_decision")
    assert dec["chosen"] == ROUTE_LOG_ONLY
    assert "log_only" in dec["reason"]
