"""Tests for the Story 6.2 inbound `self_report` handler (ground-truth affect labeling).

The client sends `{type:"self_report", ts, data:{affect, skipped, prompt_index?, section_id?}}`
at a natural pause point. The WS loop dispatches it to `_handle_self_report`, which emits a
`self_report` research event via `_safe_emit` for model validation. A deliberate skip is
`{skipped:true, affect:null}` (distinct from missing data); an out-of-vocab `affect` and a
malformed message are dropped without raising (NFR22).

We patch the research-event emitter so no live socket / model / vLLM is needed (mirror
test_ws_adaptation_interaction.py).
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


def _report_envelope(affect="confused", skipped=False, **extra):
    data = {"affect": affect, "skipped": skipped}
    data.update(extra)
    return {"type": "self_report", "ts": 1, "data": data}


async def test_valid_selection_emits_research_event(captured_events):
    await ws._handle_self_report(
        _report_envelope("confused", prompt_index=2, section_id="sec-1"), "u1", "s1"
    )

    reports = [e for e in captured_events if e["event_type"] == "self_report"]
    assert len(reports) == 1
    evt = reports[0]
    assert evt["learner_id"] == "u1"
    assert evt["session_id"] == "s1"
    assert isinstance(evt["timestamp"], int)
    assert evt["payload"] == {
        "affect": "confused",
        "skipped": False,
        "omitted": False,
        "prompt_index": 2,
        "section_id": "sec-1",
    }


@pytest.mark.parametrize("affect", ["engaged", "confused", "bored", "frustrated", "neutral"])
async def test_all_five_vocab_values_are_valid(captured_events, affect):
    """The 5-value superset (4 AFFECT_STATES + neutral) is all accepted."""
    await ws._handle_self_report(_report_envelope(affect), "u1", "s1")
    reports = [e for e in captured_events if e["event_type"] == "self_report"]
    assert len(reports) == 1
    assert reports[0]["payload"]["affect"] == affect
    assert reports[0]["payload"]["skipped"] is False


async def test_neutral_is_accepted_but_not_a_model_state():
    """Neutral is a self-report-only ground-truth label, NOT in the model AFFECT_STATES."""
    from app.agents.state import AFFECT_STATES

    assert "neutral" in ws._SELF_REPORT_AFFECTS
    assert "neutral" not in AFFECT_STATES
    assert set(AFFECT_STATES) | {"neutral"} == ws._SELF_REPORT_AFFECTS


async def test_deliberate_skip_emits_event_with_null_affect(captured_events):
    await ws._handle_self_report(
        _report_envelope(affect=None, skipped=True, prompt_index=0), "u1", "s1"
    )
    reports = [e for e in captured_events if e["event_type"] == "self_report"]
    assert len(reports) == 1
    assert reports[0]["payload"]["skipped"] is True
    assert reports[0]["payload"]["affect"] is None


async def test_skip_normalizes_affect_to_none_even_if_provided(captured_events):
    # If the client sends skipped:true alongside an affect, the handler normalizes to None.
    await ws._handle_self_report(
        _report_envelope(affect="engaged", skipped=True), "u1", "s1"
    )
    reports = [e for e in captured_events if e["event_type"] == "self_report"]
    assert len(reports) == 1
    assert reports[0]["payload"]["affect"] is None
    assert reports[0]["payload"]["skipped"] is True


async def test_omitted_prompt_emits_event_distinct_from_skip(captured_events):
    # A due prompt RANDOMLY OMITTED by the client (never shown): no affect, NOT a user skip.
    await ws._handle_self_report(
        _report_envelope(affect=None, skipped=False, omitted=True, prompt_index=3), "u1", "s1"
    )
    reports = [e for e in captured_events if e["event_type"] == "self_report"]
    assert len(reports) == 1
    payload = reports[0]["payload"]
    assert payload["omitted"] is True
    assert payload["skipped"] is False
    assert payload["affect"] is None
    assert payload["prompt_index"] == 3


async def test_omitted_normalizes_affect_to_none_even_if_provided(captured_events):
    await ws._handle_self_report(
        _report_envelope(affect="engaged", skipped=False, omitted=True), "u1", "s1"
    )
    payload = captured_events[0]["payload"]
    assert payload["omitted"] is True
    assert payload["affect"] is None


async def test_out_of_vocab_affect_is_dropped_without_raising(captured_events):
    await ws._handle_self_report(_report_envelope("happy"), "u1", "s1")
    await ws._handle_self_report(_report_envelope("bored_to_tears"), "u1", "s1")
    assert [e for e in captured_events if e["event_type"] == "self_report"] == []


async def test_missing_data_is_dropped_without_raising(captured_events):
    # No `data` key at all.
    await ws._handle_self_report({"type": "self_report", "ts": 1}, "u1", "s1")
    # `data` present but not a dict.
    await ws._handle_self_report({"type": "self_report", "ts": 1, "data": "nope"}, "u1", "s1")
    assert [e for e in captured_events if e["event_type"] == "self_report"] == []


async def test_non_skip_with_null_affect_is_dropped(captured_events):
    # Not skipped AND no valid affect → invalid, dropped.
    await ws._handle_self_report(_report_envelope(affect=None, skipped=False), "u1", "s1")
    assert [e for e in captured_events if e["event_type"] == "self_report"] == []


async def test_cycle_number_is_coerced(captured_events):
    env = _report_envelope("engaged")
    env["data"]["cycle_number"] = "7"
    await ws._handle_self_report(env, "u1", "s1")
    assert captured_events[0]["cycle_number"] == 7


async def test_optional_payload_keys_default_to_none(captured_events):
    # No prompt_index / section_id supplied → keys present with None (stable payload shape).
    await ws._handle_self_report(_report_envelope("bored"), "u1", "s1")
    payload = captured_events[0]["payload"]
    assert payload["prompt_index"] is None
    assert payload["section_id"] is None
    assert payload["omitted"] is False
