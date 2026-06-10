"""Tests for behavioral inference (Story 4.4b AC1/AC3) — ONNX-free via fake session."""

import numpy as np

from app.services.behavioral_inference import (
    BEHAVIORAL_CLASS_ORDER,
    BehavioralModel,
    _events_to_dataframe,
    predict_from_window,
)


class _FakeSession:
    def __init__(self, logits):
        self._logits = np.asarray(logits, dtype=np.float32)

    def run(self, _outputs, feeds):
        window = feeds["window"]
        assert window.shape == (1, 30, 13)          # (B, T, N_FEATURES)
        return [self._logits[np.newaxis]]


def _model(logits, mean=0.0, std=1.0):
    return BehavioralModel(
        session=_FakeSession(logits),
        stats={"mean": np.full(13, mean, np.float32), "std": np.full(13, std, np.float32)},
    )


# ── event -> DataFrame adapter (AC1) ──────────────────────────────────────────
def test_events_to_dataframe_mapping_and_windowing():
    events = [
        {"kind": "mouse_sample", "t_wall": 1000, "x": 960, "y": 540},
        {"kind": "mouse_click", "t_wall": 1100},
        {"kind": "key", "t_wall": 1200, "category": "backspace"},
        {"kind": "key", "t_wall": 1250, "category": "alpha"},
        {"kind": "scroll", "t_wall": 1300, "delta_y": 40.0},
        {"kind": "visibility", "t_wall": 1400, "state": "hidden"},   # dropped
        {"kind": "mouse_sample", "t_wall": 99000, "x": 1, "y": 1},   # out of window -> dropped
    ]
    df = _events_to_dataframe(events, capture_started_at_wall=1000)
    assert list(df["type"]) == ["move", "click", "key", "key", "scroll"]
    assert df.iloc[0]["ts"] == 0                       # window-relative
    assert abs(df.iloc[0]["x"] - 0.5) < 0.01           # 960 / 1920 nominal viewport
    assert df.iloc[2]["key"] == "Backspace"            # category=="backspace" -> Backspace
    assert df.iloc[3]["key"] == ""                     # other categories -> "" (content never read)
    assert df.iloc[4]["dy"] == 40.0


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
        stats={"mean": np.full(13, 1.0, np.float32), "std": np.full(13, 2.0, np.float32)},
    )
    predict_from_window([{"kind": "mouse_click", "t_wall": 100}], 0, model=model)
    # bin 1 has no events -> raw features all 0 -> normalized (0 - 1) / 2 = -0.5
    assert np.allclose(captured["window"][0, 1], -0.5)


def test_behavioral_class_order_differs_from_facial():
    # engaged-first order is the Bi-LSTM's; the facial model uses bored-first.
    assert BEHAVIORAL_CLASS_ORDER == ("engaged", "bored", "confused", "frustrated")
