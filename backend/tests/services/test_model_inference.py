"""Unit tests for the facial engagement inference service (Story 4.4).

These run WITHOUT the ONNX model file by injecting a fake session, so they
verify the contract-critical decode / frame-selection / softmax logic in CI.
"""

import base64

import numpy as np
import pytest

from app.services.model_inference import (
    BYTES_PER_FRAME,
    CHANNELS,
    CLASS_LABELS,
    FRAMES_PER_WINDOW,
    INPUT_SIZE,
    EngagementModel,
    decode_frames,
    predict_from_payload,
    select_window,
    _softmax,
)


def _make_payload(n: int) -> str:
    """Build a base64 payload of `n` frames with frame i filled with value i."""
    frames = np.stack([
        np.full((CHANNELS, INPUT_SIZE, INPUT_SIZE), float(i), dtype=np.float32)
        for i in range(n)
    ])
    return base64.b64encode(frames.tobytes()).decode("ascii")


class _FakeSession:
    """Stands in for onnxruntime.InferenceSession; returns fixed logits."""

    def __init__(self, logits):
        self._logits = np.asarray(logits, dtype=np.float32)
        self.last_batch = None

    def run(self, output_names, feeds):
        self.last_batch = next(iter(feeds.values()))
        return [self._logits[np.newaxis, :]]  # shape (1, 4)


# ── decode_frames ──────────────────────────────────────────────────────────────
def test_decode_frames_roundtrip():
    arr = decode_frames(_make_payload(3), 3)
    assert arr.shape == (3, CHANNELS, INPUT_SIZE, INPUT_SIZE)
    assert arr.dtype == np.float32
    assert arr[0].mean() == 0.0 and arr[2].mean() == 2.0


def test_decode_frames_empty_returns_none():
    assert decode_frames("", 0) is None
    assert decode_frames("", 5) is None
    assert decode_frames(_make_payload(1), 0) is None


def test_decode_frames_size_mismatch_raises():
    # claim 4 frames but only ship 2
    with pytest.raises(ValueError):
        decode_frames(_make_payload(2), 4)


def test_bytes_per_frame_constant():
    assert BYTES_PER_FRAME == CHANNELS * INPUT_SIZE * INPUT_SIZE * 4 == 110_592


# ── select_window ───────────────────────────────────────────────────────────────
def test_select_window_downsamples_evenly():
    frames = np.stack([np.full((CHANNELS, INPUT_SIZE, INPUT_SIZE), i, np.float32) for i in range(30)])
    win = select_window(frames)
    assert win.shape[0] == FRAMES_PER_WINDOW
    assert win[0].mean() == 0.0           # first frame kept
    assert win[-1].mean() == 29.0         # last frame kept


def test_select_window_exact_16_is_identity_order():
    frames = np.stack([np.full((CHANNELS, INPUT_SIZE, INPUT_SIZE), i, np.float32) for i in range(16)])
    win = select_window(frames)
    assert win.shape[0] == 16
    assert [int(f.mean()) for f in win] == list(range(16))


def test_select_window_pads_when_fewer_than_16():
    frames = np.stack([np.full((CHANNELS, INPUT_SIZE, INPUT_SIZE), i, np.float32) for i in range(5)])
    win = select_window(frames)
    assert win.shape[0] == FRAMES_PER_WINDOW   # padded by repeating indices
    assert win[0].mean() == 0.0 and win[-1].mean() == 4.0


# ── softmax ─────────────────────────────────────────────────────────────────────
def test_softmax_normalises_and_preserves_argmax():
    p = _softmax(np.array([0.1, 2.0, 0.3, 0.5], dtype=np.float32))
    assert pytest.approx(p.sum(), abs=1e-6) == 1.0
    assert int(p.argmax()) == 1


# ── EngagementModel.infer ───────────────────────────────────────────────────────
def test_infer_returns_level_label_probs():
    model = EngagementModel(session=_FakeSession([0.1, 0.2, 3.0, 0.4]))  # class 2 = "high"
    window = np.zeros((FRAMES_PER_WINDOW, CHANNELS, INPUT_SIZE, INPUT_SIZE), np.float32)
    out = model.infer(window)
    assert out["engagement_level"] == 2
    assert out["label"] == "high" == CLASS_LABELS[2]
    assert 0.0 <= out["confidence"] <= 1.0
    assert len(out["probs"]) == 4 and pytest.approx(sum(out["probs"]), abs=1e-6) == 1.0
    # model received a batched (1, T, 3, 96, 96) float32 tensor
    assert model._session.last_batch.shape == (1, FRAMES_PER_WINDOW, CHANNELS, INPUT_SIZE, INPUT_SIZE)


# ── predict_from_payload (end-to-end with fake model) ────────────────────────────
def test_predict_from_payload_end_to_end():
    model = EngagementModel(session=_FakeSession([5.0, 0.0, 0.0, 0.0]))  # class 0
    out = predict_from_payload(_make_payload(30), 30, model=model)
    assert out["engagement_level"] == 0
    assert out["label"] == "very_low"
    assert out["frames_used"] == FRAMES_PER_WINDOW


def test_predict_from_payload_empty_cycle_returns_none():
    model = EngagementModel(session=_FakeSession([1.0, 0.0, 0.0, 0.0]))
    assert predict_from_payload("", 0, model=model) is None
