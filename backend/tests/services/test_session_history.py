"""Session reconstruction: the join and the derived quantities.

The Monitor's timeline and its state durations are DERIVED — the system records a state per cycle
and never a duration. That arithmetic is the part most likely to be quietly wrong, and wrong in a
way that looks plausible: a learner reported as confused for four minutes when the camera was off
for three of them reads as a finding rather than a bug. These tests pin the derivation.
"""

from __future__ import annotations

import pytest

from app.services.session_history_service import (
    _cycle_state,
    _state_changes,
    _summary,
)


def cyc(n: int, at: int, *, facial=None, behavioural=None, fused=None, **extra):
    c = {"cycle_number": n, "started_at": at, "facial": facial,
         "behavioural": behavioural, "fused": fused,
         "gate": None, "strategy": None, "triggered": None, "delivered": None}
    c.update(extra)
    return c


def det(state, conf=0.9, source="facial_geometry"):
    return {"affect_state": state, "affect_confidence": conf, "affect_source": source}


# ── which channel a cycle's state comes from ──────────────────────────────────────────

def test_fusion_wins_when_present():
    """The fused reading is the combined one, so it outranks either channel alone."""
    c = cyc(1, 0, facial=det("bored"), behavioural=det("confused"), fused=det("confused", 0.7, "fusion"))
    assert _cycle_state(c) == ("confused", 0.7, "fusion")


def test_falls_back_to_a_single_channel():
    assert _cycle_state(cyc(1, 0, behavioural=det("confused", 0.8, "behavioral_model")))[0] == "confused"


def test_a_cycle_with_no_detection_resolves_to_nothing():
    """An empty cycle must not inherit the previous state."""
    assert _cycle_state(cyc(1, 0)) == (None, None, None)


# ── the derivation that matters ───────────────────────────────────────────────────────

def test_consecutive_same_state_is_one_run_not_many():
    cycles = [cyc(i, i * 30_000, facial=det("bored")) for i in range(4)]
    changes = _state_changes(cycles)
    assert len(changes) == 1
    assert changes[0]["to"] == "bored"
    assert changes[0]["cycles"] == 4
    # Still open: the session may not have ended, and inventing an end time is the alternative.
    assert changes[0]["durationMs"] is None


def test_a_transition_closes_the_previous_run_with_its_duration():
    cycles = [
        cyc(0, 0, facial=det("engaged")),
        cyc(1, 30_000, facial=det("engaged")),
        cyc(2, 60_000, facial=det("bored")),
    ]
    changes = _state_changes(cycles)
    assert [c["to"] for c in changes] == ["engaged", "bored"]
    assert changes[0]["durationMs"] == 60_000
    assert changes[1]["from"] == "engaged"
    assert changes[1]["durationMs"] is None


def test_an_observation_gap_closes_the_run_rather_than_extending_it():
    """The bug this guards: a learner who walked away being reported as bored throughout.

    Cycles 2 and 3 produced no detection. The `bored` run must end when observation stopped, not
    resume across the gap — and the state after the gap is a NEW run even though it is the same
    label, because nothing was observed in between.
    """
    cycles = [
        cyc(0, 0, facial=det("bored")),
        cyc(1, 30_000, facial=det("bored")),
        cyc(2, 60_000),                      # empty cycle - learner absent
        cyc(3, 90_000),                      # still absent
        cyc(4, 120_000, facial=det("bored")),
    ]
    changes = _state_changes(cycles)
    assert len(changes) == 2, "the gap must split the run"
    assert changes[0]["durationMs"] == 60_000, "closed when observation stopped, not at 120s"
    assert changes[1]["from"] is None, "a run after a gap has no observed predecessor"
    assert changes[0]["cycles"] == 2


def test_duration_is_never_negative_on_out_of_order_timestamps():
    cycles = [cyc(0, 60_000, facial=det("bored")), cyc(1, 0, facial=det("confused"))]
    assert _state_changes(cycles)[0]["durationMs"] == 0


# ── summary ───────────────────────────────────────────────────────────────────────────

class Row:
    def __init__(self, event_type, timestamp):
        self.event_type = event_type
        self.timestamp = timestamp


def test_summary_counts_only_cycles_that_actually_detected_something():
    cycles = [
        cyc(0, 0, facial=det("bored", 0.9)),
        cyc(1, 30_000),                                  # no detection
        cyc(2, 60_000, facial=det("confused", 0.7)),
    ]
    rows = [Row("facial_affect_detected", 0), Row("facial_affect_detected", 60_000)]
    s = _summary("sess", cycles, _state_changes(cycles), rows)
    assert s["cycleCount"] == 3
    assert s["detectionCount"] == 2, "an empty cycle is not a detection"
    assert s["meanConfidence"] == pytest.approx(0.8)
    assert s["byState"] == {"bored": 1, "confused": 1}


def test_summary_surfaces_triggered_adaptations_with_no_delivery():
    """A triggered adaptation with no delivery is the ONLY signal that delivery failed.

    The failure path logs at debug and emits no event, so this gap is the entire evidence base.
    """
    rows = [
        Row("adaptation_triggered", 0),
        Row("adaptation_triggered", 30_000),
        Row("adaptation_delivered", 30_100),
    ]
    s = _summary("sess", [], [], rows)
    assert s["interventionsTriggered"] == 2
    assert s["interventionsDelivered"] == 1
    assert s["deliveriesUnaccounted"] == 1


def test_summary_is_safe_on_an_empty_session():
    s = _summary("sess", [], [], [])
    assert s["cycleCount"] == 0
    assert s["meanConfidence"] is None
    assert s["durationMs"] is None


# ── the intervention lifecycle, once the backend records it ───────────────────────────

def test_next_state_is_the_next_cycle_that_detected_something():
    """Skips cycles that resolved to nothing — an empty cycle is not an outcome."""
    from app.services.session_history_service import _next_state_after

    cycles = [
        cyc(5, 0, facial=det("confused")),
        cyc(6, 30_000),                              # empty
        cyc(7, 60_000, facial=det("engaged", 0.8)),
    ]
    nxt = _next_state_after(cycles, 5)
    assert nxt is not None
    assert nxt["cycle_number"] == 7 and nxt["state"] == "engaged"


def test_next_state_is_none_when_the_session_ends_there():
    from app.services.session_history_service import _next_state_after
    assert _next_state_after([cyc(1, 0, facial=det("bored"))], 1) is None


def test_gaps_name_what_the_record_lacks_for_this_cycle():
    """The UI needs the reason, not a blank: a withheld gate and a discarded field look alike."""
    from app.services.session_history_service import _missing_for

    # Recorded properly: text present, reason present, delivered, response joined.
    complete = cyc(1, 0, triggered={"text": "try re-reading the example"},
                   strategy={"reason": "confusion persisted"},
                   delivered={"adaptation_id": "a"}, response={"interaction": "dismissed"})
    assert _missing_for(complete) == []

    # An older row, written before text and reason were persisted.
    older = cyc(2, 0, triggered={"variant": "show_hint"}, strategy={"action_type": "show_hint"},
                delivered={"adaptation_id": "b"})
    gaps = _missing_for(older)
    assert "hint_text" in gaps and "strategy_reason" in gaps
    assert "no_response_recorded" in gaps


def test_a_generated_hint_with_no_delivery_is_unconfirmed_not_failed():
    """Silence and a recorded failure are different claims."""
    from app.services.session_history_service import _missing_for

    unconfirmed = cyc(3, 0, triggered={"text": "x"})
    assert "delivery_unconfirmed" in _missing_for(unconfirmed)

    # An explicit failure event resolves the ambiguity, so it is no longer "unconfirmed".
    failed = cyc(4, 0, triggered={"text": "x"}, delivery_failed={"reason": "socket_unavailable"})
    assert "delivery_unconfirmed" not in _missing_for(failed)
