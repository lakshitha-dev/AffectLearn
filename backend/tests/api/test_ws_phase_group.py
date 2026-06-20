"""Tests for the Story 6.1 keystone: WS-session phase/group wiring.

These assert the WS handlers feed REAL `phase`/`group` into `make_initial_state` (vs the
old phase_a/control defaults) so the existing router can select the adaptive branch in
production. We:
  - patch `make_initial_state` to capture the args the handler passed, and
  - patch `get_graph` with a fake whose `ainvoke` echoes the seeded state, so the real
    branch decision is observable without a model file or vLLM.
Resolution itself (`_resolve_phase_group`) is tested against the real DB + study_service.
"""

import pytest

import app.api.routes.ws as ws
from app.agents.edges import route_after_profiler
from app.services import study_service

pytestmark = pytest.mark.asyncio


@pytest.fixture
def captured_events(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(ws, "emit_research_event", fake_emit)
    return events


@pytest.fixture
def capture_initial_state(monkeypatch):
    """Capture the kwargs the handler passes into make_initial_state and run the real router."""
    captured: dict = {}
    real_make = ws.make_initial_state

    def spy(**kwargs):
        captured.update(kwargs)
        return real_make(**kwargs)

    monkeypatch.setattr(ws, "make_initial_state", spy)
    return captured


class _RoutingGraph:
    """Fake compiled graph: applies the REAL router to the seeded state so the handler's
    phase/group choice drives whether an adaptation is delivered."""

    async def ainvoke(self, initial_state):
        out = {
            "affect_state": "confused",
            "affect_confidence": 0.7,
            "detection_mode": "facial_only",
            "affect_source": "engagement_adapter",
            "facial_inference": {},
            "behavioral_inference": {},
            "should_adapt": route_after_profiler(initial_state) == "pedagogical",
        }
        if out["should_adapt"]:
            out["adaptation_content"] = {
                "variant": "show_hint",
                "metadata": {"generated": True, "fallback": False},
            }
            out["delivery_message"] = {
                "type": "adaptation",
                "action": "show_hint",
                "content": {"text": "hint", "variant": "show_hint"},
                "ts": 1,
            }
        return out


def _facial_envelope(cycle=1):
    return {"type": "facial_features", "ts": 1,
            "data": {"cycle_number": cycle, "frames_captured": 30, "dropped_frames": 0,
                     "frames_b64": "AAAA"}}


# ── resolution ────────────────────────────────────────────────────────────────-

async def test_resolve_phase_group_reads_real_values(db, test_user):
    await study_service.assign_group(db, test_user.id, "adaptive")
    await study_service.set_phase(db, "phase_b")
    phase, group = await ws._resolve_phase_group(db, str(test_user.id))
    assert phase == "phase_b"
    assert group == "adaptive"


async def test_resolve_phase_group_defaults_for_unassigned(db, test_user):
    phase, group = await ws._resolve_phase_group(db, str(test_user.id))
    assert phase == "phase_a"
    assert group == "control"


async def test_resolve_phase_group_degrades_on_error():
    # db=None path returns the safe default; a glitch never routes onto adaptive.
    phase, group = await ws._resolve_phase_group(None, "u1")
    assert (phase, group) == ("phase_a", "control")


# ── handler wiring ───────────────────────────────────────────────────────────--

async def test_handler_passes_real_phase_group(
    monkeypatch, capture_initial_state, captured_events
):
    monkeypatch.setattr(ws, "get_graph", lambda: _RoutingGraph())
    monkeypatch.setattr(ws, "forced_mode", lambda: "behavioral_only")  # skip fusion pairing
    sends: list = []

    async def fake_send_to(uid, msg):
        sends.append((uid, msg))
        return True

    monkeypatch.setattr(ws.connection_manager, "send_to", fake_send_to)

    await ws._handle_facial_features(
        _facial_envelope(), "u1", "s1", None, "phase_b", "adaptive"
    )

    # The keystone assertion: real values reached make_initial_state.
    assert capture_initial_state["phase"] == "phase_b"
    assert capture_initial_state["group"] == "adaptive"
    # And the adaptive branch therefore delivered an adaptation.
    assert len(sends) == 1 and sends[0][1]["action"] == "show_hint"
    assert any(e["event_type"] == "adaptation_delivered" for e in captured_events)


async def test_phase_a_learner_routes_log_only_no_delivery(
    monkeypatch, capture_initial_state, captured_events
):
    monkeypatch.setattr(ws, "get_graph", lambda: _RoutingGraph())
    monkeypatch.setattr(ws, "forced_mode", lambda: "behavioral_only")
    sends: list = []

    async def fake_send_to(uid, msg):
        sends.append((uid, msg))
        return True

    monkeypatch.setattr(ws.connection_manager, "send_to", fake_send_to)

    # Phase A learner of the adaptive group still routes log_only (FR28).
    await ws._handle_facial_features(
        _facial_envelope(), "u1", "s1", None, "phase_a", "adaptive"
    )

    assert capture_initial_state["phase"] == "phase_a"
    assert capture_initial_state["group"] == "adaptive"
    assert sends == []  # no adaptation delivered
    assert not any(e["event_type"] == "adaptation_delivered" for e in captured_events)


async def test_behavioral_handler_passes_real_phase_group(
    monkeypatch, capture_initial_state, captured_events
):
    monkeypatch.setattr(ws, "get_graph", lambda: _RoutingGraph())
    monkeypatch.setattr(ws, "forced_mode", lambda: "facial_only")  # skip fusion pairing
    sends: list = []

    async def fake_send_to(uid, msg):
        sends.append((uid, msg))
        return True

    monkeypatch.setattr(ws.connection_manager, "send_to", fake_send_to)

    envelope = {"type": "behavioral_window", "ts": 1,
                "data": {"cycle_number": 2, "summary": {}}}
    await ws._handle_behavioral_window(
        envelope, "u2", "s2", None, "phase_b", "adaptive"
    )

    assert capture_initial_state["phase"] == "phase_b"
    assert capture_initial_state["group"] == "adaptive"
    assert len(sends) == 1 and sends[0][1]["action"] == "show_hint"


async def test_handler_defaults_when_phase_group_omitted(
    monkeypatch, capture_initial_state, captured_events
):
    # Back-compat: existing tests call the handler without phase/group → safe defaults.
    monkeypatch.setattr(ws, "get_graph", lambda: _RoutingGraph())
    monkeypatch.setattr(ws, "forced_mode", lambda: "behavioral_only")

    async def fake_send_to(uid, msg):
        return True

    monkeypatch.setattr(ws.connection_manager, "send_to", fake_send_to)

    await ws._handle_facial_features(_facial_envelope(), "u1", "s1")

    assert capture_initial_state["phase"] == "phase_a"
    assert capture_initial_state["group"] == "control"
