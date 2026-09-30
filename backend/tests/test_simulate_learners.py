"""The system-simulation harness: its synthetic signals must drive the real models as intended, and
its accounts must be the kind every research surface excludes."""

import random

from app.services import geometry_inference as gi
from app.services import behavioral_inference
from scripts.simulate_learners import (
    GEOMETRY_CHANNEL_ORDER,
    PROFILES,
    SIM_DOMAIN,
    behaviour_events,
    geometry_frames,
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
