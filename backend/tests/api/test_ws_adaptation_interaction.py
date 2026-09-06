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


# ── coordinates: the join keys analysis needs ─────────────────────────────────────────

async def test_section_and_cycle_land_in_indexed_columns_not_the_payload(captured_events):
    """The gap this closes: every learner response was unjoinable.

    The handler has always promoted both when present -- the CLIENT never sent them, so responses
    landed with `cycle_number: 0` and no section at all. That made two questions unanswerable:
    which material a hint was accepted on, and which detection cycle a response belongs to. The
    second is the join the post-intervention outcome window is built from.

    They must land as top-level COLUMNS: `research_events.section_id` is indexed and the research
    query API filters on it, while `payload` is JSON and is not queryable.
    """
    envelope = _interaction_envelope("dismissed", action="show_hint")
    envelope["data"]["section_id"] = "sec-42"
    envelope["data"]["cycle_number"] = 7

    await ws._handle_adaptation_interaction(envelope, "u1", "s1")

    evt = [e for e in captured_events if e["event_type"] == "adaptation_interaction"][0]
    assert evt["section_id"] == "sec-42"
    assert evt["cycle_number"] == 7
    assert "section_id" not in evt["payload"], "must be a column, not buried in JSON"


async def test_a_response_without_a_section_is_still_recorded(captured_events):
    """Absent coordinates must not drop the response — an unjoinable row still beats no row."""
    await ws._handle_adaptation_interaction(_interaction_envelope("accepted"), "u1", "s1")

    evt = [e for e in captured_events if e["event_type"] == "adaptation_interaction"][0]
    assert "section_id" not in evt
    assert evt["cycle_number"] == 0
