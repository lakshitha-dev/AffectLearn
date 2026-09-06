"""The post-delivery probe: the only ground truth that can speak to a specific intervention.

Everything else in the record answers a different question. `self_report` fires on section
completion, references no delivery, and arrives after the learner has left the material.
`adaptation_interaction` records dismissal, which is an action rather than an appraisal — a
learner who closes a hint may have read and used it. The detector's own later reading is the
instrument under evaluation, so it cannot also be the verdict on itself.

So this event is load-bearing for the effectiveness claim, and the distinctions it draws have to
survive: a declined probe is not a negative answer, and `unsure` is not silence.
"""

from __future__ import annotations

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


def _probe(response="helped", adaptation_id="a1", **data):
    payload = {"adaptation_id": adaptation_id, "action": "show_hint"}
    if response is not None:
        payload["response"] = response
    payload.update(data)
    return {"type": "adaptation_probe", "ts": 1, "data": payload}


def _only(events):
    rows = [e for e in events if e["event_type"] == "adaptation_probe"]
    assert len(rows) == 1, rows
    return rows[0]


# ── the three answers ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("response", ["helped", "did_not_help", "unsure"])
async def test_each_valid_response_is_recorded(captured_events, response):
    await ws._handle_adaptation_probe(_probe(response), "u1", "s1")

    evt = _only(captured_events)
    assert evt["payload"]["response"] == response
    assert evt["payload"]["dismissed"] is False
    assert evt["payload"]["adaptation_id"] == "a1"
    assert evt["learner_id"] == "u1" and evt["session_id"] == "s1"


async def test_unsure_is_an_answer_not_an_absence(captured_events):
    """Forcing "I don't know" into a pole, or into silence, would bias the appraisal either way."""
    await ws._handle_adaptation_probe(_probe("unsure"), "u1", "s1")

    payload = _only(captured_events)["payload"]
    assert payload["response"] == "unsure"
    assert payload["dismissed"] is False


# ── a declined probe is its own observation ───────────────────────────────────────────

async def test_a_declined_probe_is_recorded_but_carries_no_response(captured_events):
    """Closing the probe is not a negative answer.

    Collapsing "declined" into "did_not_help" would manufacture negative evidence; dropping it
    entirely would hide that the learner was asked at all, and the proportion of interventions
    that were actually appraised is needed to interpret the ones that were.
    """
    envelope = _probe(response=None, dismissed=True)
    await ws._handle_adaptation_probe(envelope, "u1", "s1")

    payload = _only(captured_events)["payload"]
    assert payload["dismissed"] is True
    assert payload["response"] is None


async def test_a_dismissal_does_not_need_a_valid_response_field(captured_events):
    """The learner closed it; there is nothing to validate."""
    await ws._handle_adaptation_probe(_probe(response="nonsense", dismissed=True), "u1", "s1")
    assert _only(captured_events)["payload"]["response"] is None


# ── malformed input must never break the session ──────────────────────────────────────

async def test_an_out_of_vocabulary_response_is_dropped(captured_events):
    await ws._handle_adaptation_probe(_probe("very_helpful"), "u1", "s1")
    assert captured_events == []


async def test_a_probe_without_an_adaptation_id_is_dropped(captured_events):
    """Unjoinable: it names no intervention, so it can support no claim about one."""
    envelope = {"type": "adaptation_probe", "ts": 1, "data": {"response": "helped"}}
    await ws._handle_adaptation_probe(envelope, "u1", "s1")
    assert captured_events == []


async def test_missing_data_is_dropped_without_raising(captured_events):
    await ws._handle_adaptation_probe({"type": "adaptation_probe", "ts": 1}, "u1", "s1")
    assert captured_events == []


# ── coordinates and timing ────────────────────────────────────────────────────────────

async def test_section_and_cycle_land_in_indexed_columns(captured_events):
    await ws._handle_adaptation_probe(
        _probe("helped", section_id="sec-9", cycle_number=4), "u1", "s1"
    )

    evt = _only(captured_events)
    assert evt["section_id"] == "sec-9"
    assert evt["cycle_number"] == 4


async def test_time_on_screen_is_retained(captured_events):
    """A probe answered in under a second is a different observation from one answered slowly."""
    await ws._handle_adaptation_probe(_probe("helped", shown_after_ms=30_000), "u1", "s1")
    assert _only(captured_events)["payload"]["shown_after_ms"] == 30_000


async def test_phase_and_group_ride_along_for_filtering(captured_events):
    await ws._handle_adaptation_probe(_probe("helped"), "u1", "s1", "phase_b", "adaptive")

    evt = _only(captured_events)
    assert evt["phase"] == "phase_b" and evt["group"] == "adaptive"
