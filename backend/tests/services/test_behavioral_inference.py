"""Tests for behavioral inference (Story 4.4b AC1/AC3) — ONNX-free via fake session."""

import numpy as np

from app.services.behavioral_inference import (
    BEHAVIORAL_CLASS_ORDER,
    BehavioralModel,
    _events_to_dataframe,
    predict_from_window,
)
# Derive the fixture width from the extractor so a schema bump cannot silently desynchronise
# these test doubles from the real feature vector again.
from app.services.feature_engineering import FEATURE_NAMES, N_FEATURES


class _FakeSession:
    def __init__(self, logits):
        self._logits = np.asarray(logits, dtype=np.float32)

    def run(self, _outputs, feeds):
        window = feeds["window"]
        assert window.shape == (1, 30, N_FEATURES)          # (B, T, N_FEATURES)
        return [self._logits[np.newaxis]]


def _model(logits, mean=0.0, std=1.0):
    return BehavioralModel(
        session=_FakeSession(logits),
        stats={"mean": np.full(N_FEATURES, mean, np.float32), "std": np.full(N_FEATURES, std, np.float32)},
    )


# ── event -> DataFrame adapter (AC1) ──────────────────────────────────────────
def test_events_to_dataframe_mapping_and_windowing():
    events = [
        {"kind": "mouse_sample", "t_wall": 1000, "x": 960, "y": 540},
        {"kind": "mouse_click", "t_wall": 1100},
        {"kind": "key", "t_wall": 1200, "category": "backspace"},
        {"kind": "key", "t_wall": 1250, "category": "alpha"},
        {"kind": "scroll", "t_wall": 1300, "delta_y": 40.0},
        # Schema v2: visibility is PASSED THROUGH, not dropped. It feeds blur_time_pct and
        # tab_switch_count — the frontend had been emitting these since Story 4.3 and the
        # adapter discarded them, throwing away one of the strongest disengagement signals.
        {"kind": "visibility", "t_wall": 1400, "state": "hidden"},
        {"kind": "mouse_sample", "t_wall": 99000, "x": 1, "y": 1},   # out of window -> dropped
    ]
    df = _events_to_dataframe(events, capture_started_at_wall=1000)
    assert list(df["type"]) == ["move", "click", "key", "key", "scroll", "visibility"]
    assert df.iloc[0]["ts"] == 0                       # window-relative
    assert abs(df.iloc[0]["x"] - 0.5) < 0.01           # 960 / 1920 nominal viewport
    assert df.iloc[2]["key"] == "Backspace"            # category=="backspace" -> Backspace
    assert df.iloc[3]["key"] == ""                     # other categories -> "" (content never read)
    assert df.iloc[4]["dy"] == 40.0
    # On a visibility row `dy` carries the STATE (1.0 hidden / 0.0 visible), not a delta.
    assert df.iloc[5]["dy"] == 1.0


def test_native_scroll_delta_falls_back_to_scroll_y():
    """`delta_y` is 0 for NATIVE scrolls (keyboard, scrollbar, programmatic) — only wheel sets it.

    Using it alone made every non-wheel scroll invisible to scroll_velocity_mean and
    scroll_back_runs, a large blind spot on a reading platform. The adapter now differences the
    absolute `scroll_y`, which is always present.
    """
    events = [
        {"kind": "scroll", "t_wall": 1000, "delta_y": 0.0, "scroll_y": 400.0},
        {"kind": "scroll", "t_wall": 1100, "delta_y": 0.0, "scroll_y": 520.0},   # +120 down
        {"kind": "scroll", "t_wall": 1200, "delta_y": 0.0, "scroll_y": 480.0},   # -40  up
        {"kind": "scroll", "t_wall": 1300, "delta_y": 55.0, "scroll_y": 900.0},  # wheel wins
    ]
    df = _events_to_dataframe(events, capture_started_at_wall=1000)
    assert list(df["dy"]) == [0.0, 120.0, -40.0, 55.0]


# ── inference (AC3) ───────────────────────────────────────────────────────────
def test_predict_argmax_maps_to_behavioral_class_order():
    out = predict_from_window(
        [{"kind": "mouse_click", "t_wall": 500}], 0, model=_model([0.1, 0.2, 5.0, 0.1])
    )
    assert out["affect_index"] == 2
    assert out["label"] == "confused" == BEHAVIORAL_CLASS_ORDER[2]
    assert 0.0 <= out["confidence"] <= 1.0
    assert len(out["probs"]) == 4
    assert out["n_bins"] == 30
    # aggregate feature window persisted for training (guide §7 train/serve parity)
    assert len(out["features"]) == 30 and len(out["features"][0]) == N_FEATURES


def test_missing_window_start_anchors_to_first_event(monkeypatch):
    # Real t_wall is Date.now()-scale; with start=0 a naive ts would drop everything.
    base = 1_700_000_000_000
    events = [
        {"kind": "mouse_click", "t_wall": base + 500},
        {"kind": "key", "t_wall": base + 1500, "category": "backspace"},
    ]
    df = _events_to_dataframe(events, capture_started_at_wall=0)
    assert len(df) == 2                      # anchored, not dropped
    assert df.iloc[0]["ts"] == 0             # earliest event becomes the window origin
    assert df.iloc[1]["ts"] == 1000


def test_idle_window_still_classifies_not_none():
    out = predict_from_window([], 0, model=_model([5.0, 0.1, 0.1, 0.1]))
    assert out is not None
    assert out["label"] == "engaged" == BEHAVIORAL_CLASS_ORDER[0]


def test_zscore_normalization_is_applied():
    captured = {}

    class CapSession:
        def run(self, _outputs, feeds):
            captured["window"] = feeds["window"]
            return [np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)]

    model = BehavioralModel(
        session=CapSession(),
        stats={"mean": np.full(N_FEATURES, 1.0, np.float32), "std": np.full(N_FEATURES, 2.0, np.float32)},
    )
    predict_from_window([{"kind": "mouse_click", "t_wall": 100}], 0, model=model)
    # Bin 1 has no events. Under schema v2 an inactive bin is NOT all-zeros: `idle_time_pct` and
    # `scroll_inactivity_pct` read 1.0 (nothing happened), so they normalise to (1 - 1) / 2 = 0.0
    # while every other feature is (0 - 1) / 2 = -0.5.
    bin1 = captured["window"][0, 1]
    at_rest_one = {FEATURE_NAMES.index("idle_time_pct"),
                   FEATURE_NAMES.index("scroll_inactivity_pct")}
    for i, name in enumerate(FEATURE_NAMES):
        expected = 0.0 if i in at_rest_one else -0.5
        assert np.isclose(bin1[i], expected), f"{name}: expected {expected}, got {bin1[i]}"


def test_behavioral_class_order_differs_from_facial():
    # engaged-first order is the Bi-LSTM's; the facial model uses bored-first.
    assert BEHAVIORAL_CLASS_ORDER == ("engaged", "bored", "confused", "frustrated")
