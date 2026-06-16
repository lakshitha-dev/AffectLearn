"""Tests for the Story 5.3 adaptation-delivery path in the WS handler.

The handler builds an `AgentState`, invokes the compiled graph, and (Story 5.3) pushes
any `delivery_message` the `deliver` node produced over the learner socket via
`connection_manager.send_to`, then emits an `adaptation_delivered` research event.

We monkeypatch `get_graph` to a fake whose `ainvoke` returns a controlled state, patch
`connection_manager.send_to` to capture the sent message, and patch the research-event
emitter — so no model file, vLLM, or live socket is needed.
"""

import pytest

import app.api.routes.ws as ws

pytestmark = pytest.mark.asyncio


class _FakeGraph:
    def __init__(self, result_state):
        self._result_state = result_state

    async def ainvoke(self, _initial_state):
        return self._result_state


@pytest.fixture
def captured_events(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(ws, "emit_research_event", fake_emit)
    return events


@pytest.fixture
def captured_sends(monkeypatch):
    sends: list[tuple[str, dict]] = []

    async def fake_send_to(user_id, message):
        sends.append((user_id, message))
        return True

    monkeypatch.setattr(ws.connection_manager, "send_to", fake_send_to)
    return sends


def _facial_envelope(cycle=1):
    return {"type": "facial_features", "ts": 1,
            "data": {"cycle_number": cycle, "frames_captured": 30, "dropped_frames": 0,
                     "frames_b64": "AAAA"}}


def _state_with_delivery():
    return {
        "affect_state": "confused",
        "affect_confidence": 0.7,
        "detection_mode": "facial_only",
        "affect_source": "engagement_adapter",
        "facial_inference": {},
        "adaptation_content": {
            "text": "Here's a hint.",
            "variant": "show_hint",
            "metadata": {"action_type": "show_hint", "generated": True, "fallback": False},
        },
        "delivery_message": {
            "type": "adaptation",
            "action": "show_hint",
            "content": {"text": "Here's a hint.", "variant": "show_hint"},
            "ts": 123456789,
        },
    }


async def test_producing_cycle_sends_adaptation_and_emits_event(
    monkeypatch, captured_events, captured_sends
):
    monkeypatch.setattr(ws, "get_graph", lambda: _FakeGraph(_state_with_delivery()))
    monkeypatch.setattr(ws, "forced_mode", lambda: "behavioral_only")  # skip fusion pairing

    await ws._handle_facial_features(_facial_envelope(), "u1", "s1")

    # Exactly one adaptation message pushed to the same learner.
    assert len(captured_sends) == 1
    uid, msg = captured_sends[0]
    assert uid == "u1"
    assert msg["type"] == "adaptation"
    assert msg["action"] == "show_hint"
    assert msg["content"] == {"text": "Here's a hint.", "variant": "show_hint"}

    # affect event + adaptation_delivered event both emitted.
    types = [e["event_type"] for e in captured_events]
    assert "facial_affect_detected" in types
    delivered = [e for e in captured_events if e["event_type"] == "adaptation_delivered"]
    assert len(delivered) == 1
    p = delivered[0]["payload"]
    assert p["action"] == "show_hint"
    assert p["variant"] == "show_hint"
    assert p["generated"] is True
    assert p["fallback"] is False
    assert delivered[0]["learner_id"] == "u1" and delivered[0]["session_id"] == "s1"


async def test_no_action_cycle_sends_nothing(monkeypatch, captured_events, captured_sends):
    # A Phase A / no_action cycle: affect detected but no delivery_message in state.
    state = {
        "affect_state": "engaged",
        "affect_confidence": 0.8,
        "detection_mode": "facial_only",
        "affect_source": "engagement_adapter",
        "facial_inference": {},
    }
    monkeypatch.setattr(ws, "get_graph", lambda: _FakeGraph(state))
    monkeypatch.setattr(ws, "forced_mode", lambda: "behavioral_only")

    await ws._handle_facial_features(_facial_envelope(), "u1", "s1")

    assert captured_sends == []  # no adaptation pushed
    assert not [e for e in captured_events if e["event_type"] == "adaptation_delivered"]


async def test_send_failure_is_swallowed(monkeypatch, captured_events):
    monkeypatch.setattr(ws, "get_graph", lambda: _FakeGraph(_state_with_delivery()))
    monkeypatch.setattr(ws, "forced_mode", lambda: "behavioral_only")

    async def failing_send_to(user_id, message):
        return False  # socket gone mid-cycle; send_to already logged + swallowed

    monkeypatch.setattr(ws.connection_manager, "send_to", failing_send_to)

    # Must not raise even though the send failed.
    await ws._handle_facial_features(_facial_envelope(), "u1", "s1")

    # No delivery event for a message that never reached the learner.
    assert not [e for e in captured_events if e["event_type"] == "adaptation_delivered"]


async def test_behavioral_handler_also_delivers(monkeypatch, captured_events, captured_sends):
    state = _state_with_delivery()
    state["behavioral_inference"] = {}
    monkeypatch.setattr(ws, "get_graph", lambda: _FakeGraph(state))
    monkeypatch.setattr(ws, "forced_mode", lambda: "facial_only")  # skip fusion pairing

    envelope = {"type": "behavioral_window", "ts": 1,
                "data": {"cycle_number": 2, "summary": {}}}
    await ws._handle_behavioral_window(envelope, "u2", "s2")

    assert len(captured_sends) == 1
    assert captured_sends[0][0] == "u2"
    assert captured_sends[0][1]["action"] == "show_hint"
    assert [e for e in captured_events if e["event_type"] == "adaptation_delivered"]


async def test_deliver_helper_handles_none_state(captured_sends, captured_events):
    # An inference-error cycle has result_state=None — nothing to deliver.
    await ws._deliver_adaptation(None, "u1", "s1", 1)
    assert captured_sends == []
    assert captured_events == []
