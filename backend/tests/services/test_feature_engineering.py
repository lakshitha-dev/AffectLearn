"""Tests for the ported behavioral feature extractor (Story 4.4b AC2).

Pure — no ONNX. Guards train/serve parity: FEATURE_NAMES order, the empty-window
contract, and that activity populates the expected feature columns.
"""

import pandas as pd

from app.services.feature_engineering import FEATURE_NAMES, N_FEATURES, extract_features

_COLS = ["ts", "type", "x", "y", "key", "dy"]


def test_feature_names_locked_order():
    assert N_FEATURES == 13
    assert FEATURE_NAMES[0] == "mouse_entropy"
    assert FEATURE_NAMES[3] == "click_count"
    assert FEATURE_NAMES[8] == "backspace_pct"
    assert FEATURE_NAMES[-1] == "section_dwell_time"


def test_empty_events_yield_all_zero_window():
    out = extract_features(pd.DataFrame(columns=_COLS), window_start=0)
    assert out.shape == (30, N_FEATURES)
    assert (out == 0).all()


def test_none_events_yield_all_zero_window():
    out = extract_features(None, window_start=0)
    assert out.shape == (30, N_FEATURES)
    assert (out == 0).all()


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
    # only bin 0 had events; the rest stay zero
    assert (out[1:] == 0).all()
