"""Unit tests for the adaptation gate (pure — no Redis, no DB, no LLM).

The gate is what makes an imperfect detector usable: it converts detector error into inaction
rather than into a wrong intervention. These tests pin each withholding reason independently so
a threshold change cannot silently disable one of them.
"""

import pytest

from app.agents import edges
from app.agents.edges import (
    ADAPT_MIN_CONFIDENCE,
    GATE_COOLDOWN,
    GATE_LOW_CONFIDENCE,
    GATE_NO_AFFECT,
    GATE_NOT_ELIGIBLE,
    GATE_NOT_SUSTAINED,
    GATE_OK,
    GATE_STATE_NOT_ACTIONABLE,
    ROUTE_LOG_ONLY,
    ROUTE_PEDAGOGICAL,
    adaptation_decision,
    passes_adaptation_gate,
    route_after_profiler,
)

HIGH = max(ADAPT_MIN_CONFIDENCE, 0.9)
LOW = ADAPT_MIN_CONFIDENCE - 0.2


def gate(state="confused", conf=HIGH, history=("confused", "confused"), cycle=10, last=None):
    return passes_adaptation_gate(state, conf, list(history), cycle, last)


# ---------------------------------------------------------------- the happy path

def test_sustained_confident_actionable_state_passes():
    allowed, reason = gate()
    assert allowed is True
    assert reason == GATE_OK


@pytest.mark.parametrize("affect", ["bored", "confused", "frustrated"])
def test_all_three_actionable_states_can_pass(affect):
    allowed, reason = gate(state=affect, history=(affect, affect))
    assert allowed is True, reason


# ---------------------------------------------------------------- each withholding reason

def test_engaged_never_triggers_an_intervention():
    """Engagement is the do-nothing state, and the state the detector is worst at."""
    allowed, reason = gate(state="engaged", history=("engaged", "engaged"))
    assert allowed is False
    assert reason == GATE_STATE_NOT_ACTIONABLE


def test_missing_affect_is_withheld():
    allowed, reason = gate(state=None)
    assert allowed is False
    assert reason == GATE_NO_AFFECT


def test_low_confidence_is_withheld():
    """A 0.26-confidence guess must not drive the same action as a 0.95 one."""
    allowed, reason = gate(conf=LOW)
    assert allowed is False
    assert reason == GATE_LOW_CONFIDENCE


def test_confidence_exactly_at_threshold_passes():
    allowed, reason = gate(conf=ADAPT_MIN_CONFIDENCE)
    assert allowed is True, reason


def test_none_confidence_is_treated_as_zero():
    allowed, reason = gate(conf=None)
    assert allowed is False
    assert reason == GATE_LOW_CONFIDENCE


def test_single_cycle_state_is_not_sustained():
    """One cycle of confusion is noise; the thesis specifies two or more."""
    allowed, reason = gate(history=("engaged", "confused"))
    assert allowed is False
    assert reason == GATE_NOT_SUSTAINED


def test_flip_flopping_never_sustains():
    allowed, reason = gate(history=("confused", "bored", "confused"))
    # last 2 are (bored, confused) -> not all equal to the current state
    assert allowed is False
    assert reason == GATE_NOT_SUSTAINED


def test_history_shorter_than_the_requirement_is_withheld():
    allowed, reason = gate(history=("confused",))
    assert allowed is False
    assert reason == GATE_NOT_SUSTAINED


def test_empty_history_is_withheld():
    allowed, reason = gate(history=())
    assert allowed is False
    assert reason == GATE_NOT_SUSTAINED


def test_cooldown_blocks_a_rapid_second_adaptation():
    allowed, reason = gate(cycle=11, last=10)
    assert allowed is False
    assert reason == GATE_COOLDOWN


def test_cooldown_expires():
    allowed, reason = gate(cycle=10 + edges.ADAPT_COOLDOWN_CYCLES, last=10)
    assert allowed is True, reason


def test_no_previous_adaptation_means_no_cooldown():
    allowed, reason = gate(cycle=1, last=None)
    assert allowed is True, reason


# ---------------------------------------------------------------- eligibility interaction

@pytest.mark.parametrize(
    "phase,group",
    [("phase_a", "control"), ("phase_a", "adaptive"), ("phase_b", "control")],
)
def test_ineligible_cohorts_short_circuit_before_the_gate(phase, group):
    """Phase A and the control group are never adapted, however confident the detector is."""
    state = {
        "phase": phase, "group": group,
        "affect_state": "confused", "affect_confidence": 1.0, "cycle_number": 9,
    }
    allowed, reason = adaptation_decision(state, {"affect_history": ["confused"] * 5}, None)
    assert allowed is False
    assert reason == GATE_NOT_ELIGIBLE


def test_eligible_and_gated_passes():
    state = {
        "phase": "phase_b", "group": "adaptive",
        "affect_state": "frustrated", "affect_confidence": HIGH, "cycle_number": 9,
    }
    allowed, reason = adaptation_decision(state, {"affect_history": ["frustrated"] * 3}, None)
    assert allowed is True
    assert reason == GATE_OK


def test_eligible_but_gate_withholds():
    state = {
        "phase": "phase_b", "group": "adaptive",
        "affect_state": "confused", "affect_confidence": LOW, "cycle_number": 9,
    }
    allowed, reason = adaptation_decision(state, {"affect_history": ["confused"] * 3}, None)
    assert allowed is False
    assert reason == GATE_LOW_CONFIDENCE


def test_decision_uses_the_supplied_profile_not_state():
    """Guards the staleness bug: the gate must read the FRESH profile passed in.

    `state["learner_profile"]` still holds the PREVIOUS cycle's history when the profiler makes
    the decision, so reading from state would evaluate persistence one cycle behind.
    """
    state = {
        "phase": "phase_b", "group": "adaptive",
        "affect_state": "bored", "affect_confidence": HIGH, "cycle_number": 5,
        "learner_profile": {"affect_history": ["engaged", "engaged"]},   # stale
    }
    fresh = {"affect_history": ["bored", "bored"]}                       # current
    allowed, reason = adaptation_decision(state, fresh, None)
    assert allowed is True, reason


# ---------------------------------------------------------------- routing

def test_router_honours_the_gate_flag():
    base = {"phase": "phase_b", "group": "adaptive"}
    assert route_after_profiler({**base, "should_adapt": True}) == ROUTE_PEDAGOGICAL
    assert route_after_profiler({**base, "should_adapt": False}) == ROUTE_LOG_ONLY


def test_router_falls_back_to_eligibility_when_the_flag_is_absent():
    """Keeps the router usable standalone and preserves the Story 4.4 / 6.1 routing tests."""
    assert route_after_profiler({"phase": "phase_b", "group": "adaptive"}) == ROUTE_PEDAGOGICAL
    assert route_after_profiler({"phase": "phase_a", "group": "adaptive"}) == ROUTE_LOG_ONLY
    assert route_after_profiler({}) == ROUTE_LOG_ONLY
