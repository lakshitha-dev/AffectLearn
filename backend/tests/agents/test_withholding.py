"""The randomised trial arm: the draw, the arms, and cooldown parity between them.

WHY THIS FILE EXISTS

The system deliberately withholds help from some cycles that qualified for it. That is the control
arm, and the entire causal claim of the study rests on it being drawn correctly. Three properties
have to hold, and each one fails silently if it does not:

  * The withheld set must be drawn from EXACTLY the eligible set. Withhold a cycle that would have
    failed the gate anyway and the control arm contains unmatched observations, which biases the
    contrast in an unknown direction.
  * Both arms must consume the cooldown identically. If the withheld arm does not, it becomes
    eligible again sooner, drifts to a higher trigger rate, and stops being matched.
  * The assignment must be reproducible from the record. A PRNG makes historical arms
    unauditable — nobody could re-derive months later which arm a cycle was in.

None of these produce a visible failure at runtime. They produce a plausible-looking result.
"""

from __future__ import annotations

import pytest

from app.agents import edges
from app.agents.edges import (
    ARM_DELIVERED,
    ARM_WITHHELD,
    GATE_COOLDOWN,
    GATE_LOW_CONFIDENCE,
    GATE_OK,
    GATE_STATE_NOT_ACTIONABLE,
    GATE_WITHHELD_RANDOM,
    adaptation_decision,
    arm_for,
    consumes_cooldown,
    withhold_draw,
)


@pytest.fixture
def withholding_on():
    """Re-enable the draw, which tests/conftest.py disables by default."""
    original = edges.ADAPT_WITHHOLD_RATE
    edges.ADAPT_WITHHOLD_RATE = 0.35
    yield 0.35
    edges.ADAPT_WITHHOLD_RATE = original


def _state(**over):
    s = {
        "phase": "phase_b",
        "group": "adaptive",
        "learner_id": "L1",
        "session_id": "S1",
        "cycle_number": 5,
        "affect_state": "bored",
        "affect_confidence": 0.95,
        "affect_source": "facial_geometry",
    }
    s.update(over)
    return s


def _profile(state="bored", n=4):
    return {"affect_history_by_source": {"facial_geometry": [state] * n}}


# ── the draw ──────────────────────────────────────────────────────────────────────────

def test_the_draw_is_reproducible_from_the_cycle_identity_alone():
    """The property that makes historical arms auditable months later."""
    a = withhold_draw("L1", "S1", 7)
    b = withhold_draw("L1", "S1", 7)
    assert a == b


def test_different_cycles_draw_independently():
    draws = {withhold_draw("L1", "S1", i) for i in range(50)}
    assert len(draws) == 50, "a collision here would correlate arms across cycles"


def test_different_learners_draw_independently():
    assert withhold_draw("L1", "S1", 5) != withhold_draw("L2", "S1", 5)


def test_the_draw_is_uniform_enough_to_hit_the_target_rate():
    """A biased hash would silently skew the allocation ratio away from the configured rate."""
    n = 4000
    withheld = sum(1 for i in range(n) if withhold_draw("L", "S", i) < 0.35)
    assert 0.32 < withheld / n < 0.38, f"observed {withheld / n:.3f}, expected ~0.35"


def test_draws_stay_in_the_unit_interval():
    assert all(0.0 <= withhold_draw("L", "S", i) < 1.0 for i in range(200))


# ── only eligible cycles enter the trial ──────────────────────────────────────────────

def test_only_cycles_that_cleared_every_gate_can_be_withheld(withholding_on):
    """The failure this guards: unmatched observations contaminating the control arm.

    A cycle that fails the gate must report WHY it failed. If the draw were applied first, some
    of those cycles would be labelled `withheld_random` instead, and the control arm would then
    contain cycles the delivered arm could never contain.
    """
    # Fails on confidence, well under the geometry floor of 0.70.
    _, reason = adaptation_decision(_state(affect_confidence=0.1), _profile(), None)
    assert reason == GATE_LOW_CONFIDENCE

    # Fails on the state not being actionable.
    _, reason = adaptation_decision(_state(affect_state="engaged"), _profile("engaged"), None)
    assert reason == GATE_STATE_NOT_ACTIONABLE

    # Fails on cooldown.
    _, reason = adaptation_decision(_state(cycle_number=6), _profile(), 5)
    assert reason == GATE_COOLDOWN


def test_an_ineligible_cycle_belongs_to_no_arm():
    """A null arm is not a control observation — it is a cycle that never qualified."""
    assert arm_for(GATE_LOW_CONFIDENCE) is None
    assert arm_for(GATE_COOLDOWN) is None
    assert arm_for(GATE_STATE_NOT_ACTIONABLE) is None
    assert arm_for(GATE_OK) == ARM_DELIVERED
    assert arm_for(GATE_WITHHELD_RANDOM) == ARM_WITHHELD


def test_both_arms_occur_over_a_run_of_qualifying_cycles(withholding_on):
    """Sanity: the draw actually splits. A constant would pass every other test in this file."""
    reasons = set()
    for c in range(40):
        # Vary the session so the cooldown never binds; every cycle here qualifies.
        _, reason = adaptation_decision(
            _state(session_id=f"S{c}", cycle_number=c + 2), _profile(), None
        )
        reasons.add(reason)
    assert reasons == {GATE_OK, GATE_WITHHELD_RANDOM}


def test_rate_zero_disables_the_trial_entirely():
    """The demo path: every eligible cycle is delivered, nothing is withheld."""
    original = edges.ADAPT_WITHHOLD_RATE
    edges.ADAPT_WITHHOLD_RATE = 0.0
    try:
        for c in range(30):
            allowed, reason = adaptation_decision(
                _state(session_id=f"S{c}", cycle_number=c + 2), _profile(), None
            )
            assert allowed is True and reason == GATE_OK
    finally:
        edges.ADAPT_WITHHOLD_RATE = original


def test_rate_one_withholds_every_eligible_cycle():
    original = edges.ADAPT_WITHHOLD_RATE
    edges.ADAPT_WITHHOLD_RATE = 1.0
    try:
        allowed, reason = adaptation_decision(_state(), _profile(), None)
        assert allowed is False and reason == GATE_WITHHELD_RANDOM
    finally:
        edges.ADAPT_WITHHOLD_RATE = original


# ── cooldown parity: the property that keeps the arms matched ─────────────────────────

def test_both_arms_consume_the_cooldown():
    """If the withheld arm did not spend it, the control arm would trigger more often.

    The arms would then differ in how recently the learner was last considered — a difference the
    analysis has no way to see and no way to adjust for.
    """
    assert consumes_cooldown(GATE_OK) is True
    assert consumes_cooldown(GATE_WITHHELD_RANDOM) is True


def test_a_failed_gate_does_not_consume_the_cooldown():
    """Only a cycle that reached the trial spends the window; a rejected one costs nothing."""
    for reason in (GATE_LOW_CONFIDENCE, GATE_COOLDOWN, GATE_STATE_NOT_ACTIONABLE):
        assert consumes_cooldown(reason) is False, reason


# ── the per-session cap ───────────────────────────────────────────────────────────────

def test_the_cap_counts_both_arms_so_they_end_together(withholding_on):
    """The failure this guards: arms covering different parts of the session.

    Capping only DELIVERED interventions would stop the delivered arm at the limit while the
    withheld arm carried on accruing controls through the rest of the session. Later observations
    would then exist in one arm only, and any drift over a session — fatigue, the material getting
    harder — would load entirely onto the control group.
    """
    from app.agents.edges import ADAPT_MAX_PER_SESSION, GATE_SESSION_CAP

    profile = _profile()
    profile["adaptation_session_id"] = "S1"
    profile["eligible_this_session"] = ADAPT_MAX_PER_SESSION

    allowed, reason = adaptation_decision(_state(), profile, None)
    assert (allowed, reason) == (False, GATE_SESSION_CAP)


def test_the_cap_is_reported_as_its_own_reason_not_as_a_gate_failure():
    """`session_cap` must be distinguishable: the cycle qualified, the allowance ran out."""
    from app.agents.edges import GATE_SESSION_CAP

    assert arm_for(GATE_SESSION_CAP) is None
    assert consumes_cooldown(GATE_SESSION_CAP) is False


def test_a_count_from_a_previous_session_does_not_suppress_this_one():
    """cycle_number restarts each session while the profile outlives it.

    The same class of bug the cooldown marker already carries a session stamp for: a count left by
    a longer earlier session would suppress interventions from this session's very first cycle.
    """
    from app.agents.edges import ADAPT_MAX_PER_SESSION, _session_cap_reached

    profile = {"adaptation_session_id": "OLD", "eligible_this_session": ADAPT_MAX_PER_SESSION}
    assert _session_cap_reached(profile, "NEW") is False


def test_recording_a_cycle_resets_the_counter_on_a_new_session():
    from app.agents.edges import record_eligible_cycle

    profile = {"adaptation_session_id": "OLD", "eligible_this_session": 5}
    record_eligible_cycle(profile, "NEW")
    assert profile["adaptation_session_id"] == "NEW"
    assert profile["eligible_this_session"] == 1


def test_the_counter_accumulates_within_one_session():
    from app.agents.edges import record_eligible_cycle

    profile: dict = {}
    for _ in range(3):
        record_eligible_cycle(profile, "S1")
    assert profile["eligible_this_session"] == 3
