"""The system-simulation harness: its synthetic signals must drive the real models as intended, and
its accounts must be the kind every research surface excludes."""

import random
from types import SimpleNamespace

from app.services import geometry_inference as gi
from app.services import behavioral_inference, performance_signals
from scripts.simulate_learners import (
    GEOMETRY_CHANNEL_ORDER,
    PROFILES,
    SIM_DOMAIN,
    STRUGGLE,
    Sim,
    behaviour_events,
    behavioural_by_state,
    cards_by_source,
    decision_runs,
    geometry_frames,
    leaves_section,
    new_counters,
    performance_window,
    struggle,
)


def _p_disengaged(state: str, n: int = 20) -> float:
    rng = random.Random(1)
    ps = []
    for _ in range(n):
        frames, with_face = geometry_frames(state, rng)
        out = gi.predict_from_payload({"geometry": frames})
        if out is not None:
            ps.append(out["probs"][1])
    return sum(ps) / len(ps)


def test_scripted_faces_read_as_intended():
    # Guards the probing that chose GEOMETRY: if the model is retrained, the harness must follow.
    assert _p_disengaged("engaged") < 0.3
    assert _p_disengaged("bored") > 0.8


def test_frames_follow_the_browser_contract():
    frames, with_face = geometry_frames("bored", random.Random(3))
    assert len(frames) == 10
    assert all(len(f) == len(GEOMETRY_CHANNEL_ORDER) for f in frames)
    found = GEOMETRY_CHANNEL_ORDER.index("face_found")
    assert with_face == sum(1 for f in frames if f[found] == 1.0)


def test_behaviour_windows_are_accepted_by_feature_extraction():
    events = behaviour_events("confused", 1_790_000_000_000, random.Random(4))
    assert {e["kind"] for e in events} <= {"mouse_sample", "mouse_click", "key", "scroll"}
    assert all("key" not in e for e in events)          # categories only, never key values
    feats = behavioral_inference.extract_window_features(events, 1_790_000_000_000)
    assert feats["n_bins"] == 30


def test_profiles_are_proper_distributions():
    for profile in PROFILES.values():
        for row in profile.values():
            assert abs(sum(row.values()) - 1.0) < 1e-9


def test_simulated_accounts_use_their_own_domain():
    assert SIM_DOMAIN != "pilot.affectlearn.io"


# ── performance channel ────────────────────────────────────────────────────────


def _sim(state: str = "confused", seed: int = 5) -> Sim:
    sim = Sim("SIM001", "sim001@x", "pw", "struggling", "adaptive", random.Random(seed))
    sim.state = state
    return sim


SECTION_WITH_EXERCISE = {"id": "s1", "contentBlocks": [{"blockType": "exercise"}]}


def test_performance_window_matches_the_browser_hook():
    """Key for key what `frontend/src/hooks/use-performance-window.ts` sends."""
    window = performance_window(new_counters(1_000), "s1", 3, 61_000)
    assert set(window) == {"cycle_number", "section_id", "back_nav_count", "show_answer_used",
                           "quiz_attempt_count", "quiz_incorrect_count", "time_on_section_s"}
    assert window["time_on_section_s"] == 60.0


def test_a_confused_learner_leaves_struggle_evidence():
    sim, counters = _sim("confused"), new_counters(0)
    for _ in range(20):
        struggle(sim, counters, SECTION_WITH_EXERCISE)
    assert counters["back_nav_count"] > 0
    assert counters["show_answer_used"] is True


def test_an_engaged_learner_never_reveals_an_answer():
    sim, counters = _sim("engaged"), new_counters(0)
    for _ in range(50):
        struggle(sim, counters, SECTION_WITH_EXERCISE)
    assert counters["show_answer_used"] is False


def test_scripted_struggle_can_reach_the_pilot_floor():
    """What one confused visit can produce on a section with one quiz and an exercise: one wrong
    answer, a revealed answer and two re-reads = 0.50, over the pilot floor of 0.45."""
    counters = {**new_counters(0), "quiz_attempt_count": 1, "quiz_incorrect_count": 1,
                "show_answer_used": True, "back_nav_count": 2}
    reading = performance_signals.detect(performance_window(counters, "s1", 1, 60_000))
    assert reading is not None and reading["affect_confidence"] >= 0.45


def test_a_confused_learner_lingers_on_the_section():
    """Staying longer is what makes the slow-pace term count."""
    assert leaves_section(_sim("engaged"), 4)
    assert not leaves_section(_sim("confused"), 4)
    assert leaves_section(_sim("confused"), 4 + STRUGGLE["linger"]["confused"])


def test_struggle_probabilities_are_probabilities():
    for key in ("reread", "reveal"):
        assert all(0.0 <= p <= 1.0 for p in STRUGGLE[key].values())


# ── report ────────────────────────────────────────────────────────────────────


def _event(event_type, decision_id=None, payload=None, learner_id="u1", cycle_number=0):
    return SimpleNamespace(event_type=event_type, decision_id=decision_id, payload=payload or {},
                           learner_id=learner_id, cycle_number=cycle_number)


def test_each_card_is_attributed_to_the_channel_that_triggered_it():
    events = [
        _event("performance_signal_detected", "d1"),
        _event("learner_profile_updated", "d1", {"affect_source": "performance"}),
        _event("adaptation_delivered", "d1"),
        _event("help_requested", "d2"),
        _event("learner_profile_updated", "d2", {"affect_source": "learner_request"}),
        _event("adaptation_delivered", "d2"),
        _event("facial_affect_detected", "d3"),                 # detected, but no card
        _event("learner_profile_updated", "d3", {"affect_source": "facial_geometry"}),
    ]
    assert cards_by_source(decision_runs(events)) == {"performance": 1, "learner_request": 1}


def test_behavioural_readings_are_grouped_by_the_scripted_state():
    sim = _sim()
    sim.user_id, sim.timeline = "u1", {1: "confused", 2: "engaged"}
    events = [
        _event("behavioral_affect_detected", payload={"p_confused": 0.2}, cycle_number=1),
        _event("behavioral_affect_detected", payload={"p_confused": 0.8}, cycle_number=1),
        _event("behavioral_affect_detected", payload={"p_confused": 0.1}, cycle_number=2),
        _event("behavioral_affect_detected", payload={"idle": True}, cycle_number=2),   # no reading
    ]
    table = behavioural_by_state([sim], events)
    assert table["confused"] == {"n": 2, "mean": 0.5, "max": 0.8, "share_at_floor": 0.5}
    assert table["engaged"]["n"] == 1
