"""Tests for the ported behavioral feature extractor (schema v2).

Pure — no ONNX. Guards train/serve parity: FEATURE_NAMES order, the empty-window contract, and
that activity populates the expected feature columns.

SCHEMA v2 CHANGED THE EMPTY-WINDOW CONTRACT, deliberately. v1 returned all zeros for a silent
window, which told the model the OPPOSITE of the truth: a window with no events is maximally idle
with no scroll activity, so `idle_time_pct` and `scroll_inactivity_pct` must read 1.0, not 0.0.
Under v1 those two features were event-COUNT deficits rather than clocks, and their zero-fill on
empty bins made them a bimodal "is this bin empty?" flag — which is why a keyboard-only corpus
read as 1.0 idle in every populated bin no matter how fast the participant typed.
"""

import pandas as pd

from app.services.feature_engineering import (
    FEATURE_SCHEMA_VERSION,
    FEATURE_NAMES,
    N_FEATURES,
    extract_features,
)

_COLS = ["ts", "type", "x", "y", "key", "dy"]

# Features that are 1.0 (not 0.0) in the absence of any activity.
_IDLE_AT_REST = ("idle_time_pct", "scroll_inactivity_pct")


def _at_rest(vec) -> bool:
    """True if a feature vector is the correct 'nothing happened' vector."""
    f = dict(zip(FEATURE_NAMES, vec))
    return all(
        (f[name] == 1.0) if name in _IDLE_AT_REST else (f[name] == 0.0)
        for name in FEATURE_NAMES
    )


def test_schema_version_and_width_agree():
    assert FEATURE_SCHEMA_VERSION == 2
    assert N_FEATURES == 16 == len(FEATURE_NAMES)
    assert len(set(FEATURE_NAMES)) == N_FEATURES, "feature names must be unique"


def test_feature_names_locked_order():
    # The tensor column order depends on this; changing it silently invalidates every
    # exported model and every persisted window.
    assert FEATURE_NAMES == [
        "mouse_entropy", "mouse_velocity_mean", "mouse_velocity_std", "click_count",
        "hover_dwell_mean",
        "keystroke_count", "typing_rhythm_std", "backspace_pct", "pause_count",
        "scroll_velocity_mean", "scroll_direction_changes", "scroll_back_runs",
        "scroll_inactivity_pct",
        "idle_time_pct", "blur_time_pct", "tab_switch_count",
    ]


def test_v1_names_that_lied_are_gone():
    """`section_dwell_time` measured neither a section nor a dwell — it must not come back."""
    assert "section_dwell_time" not in FEATURE_NAMES


def test_empty_events_yield_a_fully_idle_window():
    out = extract_features(pd.DataFrame(columns=_COLS), window_start=0)
    assert out.shape == (30, N_FEATURES)
    assert all(_at_rest(row) for row in out), "an empty window is IDLE, not all-zeros"


def test_none_events_yield_a_fully_idle_window():
    out = extract_features(None, window_start=0)
    assert out.shape == (30, N_FEATURES)
    assert all(_at_rest(row) for row in out)


def test_active_first_bin_populates_features():
    rows = [(i * 100, "move", 0.1 + 0.05 * i, 0.2, "", 0.0) for i in range(8)]
    rows += [
        (500, "click", 0.0, 0.0, "", 0.0),
        (100, "key", 0.0, 0.0, "a", 0.0),
        (300, "key", 0.0, 0.0, "Backspace", 0.0),
        (200, "scroll", 0.0, 0.0, "", 30.0),
        (400, "scroll", 0.0, 0.0, "", -20.0),
    ]
    out = extract_features(pd.DataFrame(rows, columns=_COLS), window_start=0)
    f = dict(zip(FEATURE_NAMES, out[0]))
    assert f["click_count"] == 1.0
    assert f["keystroke_count"] == 2.0
    assert f["backspace_pct"] == 0.5                 # 1 of 2 keys is Backspace
    assert f["mouse_velocity_mean"] > 0.0
    assert f["scroll_direction_changes"] == 1.0      # +30 then -20 -> one sign flip
    assert f["scroll_back_runs"] == 1.0              # one upward episode
    assert f["idle_time_pct"] < 1.0                  # the bin was busy
    # Only bin 0 had events; the remainder are at rest (idle 1.0, everything else 0.0).
    assert all(_at_rest(row) for row in out[1:])


def test_idle_is_a_clock_not_a_mouse_count():
    """The v1 bug: a keyboard-only bin read as fully idle. It must now read as busy."""
    typing = [(t, "key", 0.0, 0.0, "a", 0.0) for t in range(0, 1000, 100)]
    out = extract_features(pd.DataFrame(typing, columns=_COLS), window_start=0)
    f = dict(zip(FEATURE_NAMES, out[0]))
    assert f["keystroke_count"] == 10.0
    assert f["idle_time_pct"] == 0.0, "ten keystroke events in one second is not idle"


def test_idle_is_continuous_not_bimodal():
    sparse = [(0, "key", 0.0, 0.0, "a", 0.0), (900, "key", 0.0, 0.0, "a", 0.0)]
    out = extract_features(pd.DataFrame(sparse, columns=_COLS), window_start=0)
    idle = dict(zip(FEATURE_NAMES, out[0]))["idle_time_pct"]
    assert 0.0 < idle < 1.0, f"two sparse events should be partially idle, got {idle}"


def test_scroll_back_runs_counts_episodes_not_ticks():
    """Re-reading is one signal however many wheel ticks it took — the point of using runs."""
    rows = [
        (50, "scroll", 0.0, 0.0, "", 100.0),
        (300, "scroll", 0.0, 0.0, "", -80.0),    # up-episode 1 ...
        (350, "scroll", 0.0, 0.0, "", -90.0),
        (400, "scroll", 0.0, 0.0, "", -70.0),    # ... three ticks, one episode
        (600, "scroll", 0.0, 0.0, "", 110.0),
        (800, "scroll", 0.0, 0.0, "", -60.0),    # up-episode 2
    ]
    f = dict(zip(FEATURE_NAMES, extract_features(pd.DataFrame(rows, columns=_COLS), 0)[0]))
    assert f["scroll_back_runs"] == 2.0
    assert f["scroll_direction_changes"] == 3.0   # strictly more than the episode count


def test_blur_state_integrates_across_bin_boundaries():
    rows = [
        (0, "key", 0.0, 0.0, "a", 0.0),
        (2500, "visibility", 0.0, 0.0, "", 1.0),   # hidden, mid-bin 2
        (5500, "visibility", 0.0, 0.0, "", 0.0),   # visible again, mid-bin 5
    ]
    out = extract_features(pd.DataFrame(rows, columns=_COLS), window_start=0)
    blur = [dict(zip(FEATURE_NAMES, row))["blur_time_pct"] for row in out]
    switches = [dict(zip(FEATURE_NAMES, row))["tab_switch_count"] for row in out]
    assert blur[1] == 0.0
    assert blur[2] == 0.5 and blur[5] == 0.5      # partial bins at each transition
    assert blur[3] == 1.0 and blur[4] == 1.0      # wholly hidden in between
    assert blur[6] == 0.0
    assert switches[2] == 1.0 and switches[5] == 1.0
    assert sum(switches) == 2.0


def test_visibility_events_alone_do_not_count_as_activity():
    """Leaving the tab is not input — an otherwise silent bin stays idle."""
    rows = [(100, "visibility", 0.0, 0.0, "", 1.0)]
    f = dict(zip(FEATURE_NAMES, extract_features(pd.DataFrame(rows, columns=_COLS), 0)[0]))
    assert f["idle_time_pct"] == 1.0
    assert f["tab_switch_count"] == 1.0
