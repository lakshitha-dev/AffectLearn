"""Tests for the Story 5.6 inbound `adaptation_interaction` handler (FR22 dismissal logging).

The client sends `{type:"adaptation_interaction", ts, data:{adaptation_id, action, interaction}}`
when the learner accepts/dismisses/applies a delivered adaptation. The WS loop dispatches it to
`_handle_adaptation_interaction`, which emits an `adaptation_interaction` research event via
`_safe_emit` for the Learner Profiler. Malformed input is dropped without raising (NFR22).

We patch the research-event emitter so no live socket / model / vLLM is needed.
"""

import pytest

import app.api.routes.ws as ws

pytestmark = pytest.mark.asyncio


@pytest.fixture
def captured_events(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(ws, "emit_research_event", fake_emit)
    return events


def _interaction_envelope(interaction="dismissed", action="skip_ahead", adaptation_id="a1"):
    return {
        "type": "adaptation_interaction",
        "ts": 1,
        "data": {
            "adaptation_id": adaptation_id,
            "action": action,
            "interaction": interaction,
        },
    }


async def test_dismissed_interaction_emits_research_event(captured_events):
    await ws._handle_adaptation_interaction(_interaction_envelope("dismissed"), "u1", "s1")

    interactions = [e for e in captured_events if e["event_type"] == "adaptation_interaction"]
    assert len(interactions) == 1
    evt = interactions[0]
    assert evt["learner_id"] == "u1"
    assert evt["session_id"] == "s1"
    assert isinstance(evt["timestamp"], int)
    assert evt["payload"] == {
        "adaptation_id": "a1",
        "action": "skip_ahead",
        "interaction": "dismissed",
    }


async def test_accepted_and_applied_interactions_are_valid(captured_events):
    await ws._handle_adaptation_interaction(_interaction_envelope("accepted"), "u1", "s1")
    await ws._handle_adaptation_interaction(
        _interaction_envelope("applied", action="increase_difficulty"), "u1", "s1"
    )
    kinds = [e["payload"]["interaction"] for e in captured_events]
    assert kinds == ["accepted", "applied"]


async def test_missing_data_is_dropped_without_raising(captured_events):
    # No `data` key at all.
    await ws._handle_adaptation_interaction({"type": "adaptation_interaction", "ts": 1}, "u1", "s1")
    # `data` present but not a dict.
    await ws._handle_adaptation_interaction(
        {"type": "adaptation_interaction", "ts": 1, "data": "nope"}, "u1", "s1"
    )
    assert [e for e in captured_events if e["event_type"] == "adaptation_interaction"] == []


async def test_unknown_interaction_is_dropped_without_raising(captured_events):
    await ws._handle_adaptation_interaction(
        _interaction_envelope("clicked_through"), "u1", "s1"
    )
    # Missing interaction entirely.
    await ws._handle_adaptation_interaction(
        {"type": "adaptation_interaction", "ts": 1, "data": {"adaptation_id": "a1"}}, "u1", "s1"
    )
    assert [e for e in captured_events if e["event_type"] == "adaptation_interaction"] == []


async def test_cycle_number_is_coerced(captured_events):
    env = _interaction_envelope("dismissed")
    env["data"]["cycle_number"] = "7"
    await ws._handle_adaptation_interaction(env, "u1", "s1")
    assert captured_events[0]["cycle_number"] == 7
