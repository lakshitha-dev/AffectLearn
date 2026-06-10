"""Facial engagement inference service (Story 4.4).

Consumes the `facial_features` WebSocket payload produced by the browser
(`frontend/src/lib/preprocess.ts` / `useMediaPipe`) and runs the CNN-LSTM
engagement model exported to ONNX (`cnn_lstm_best.onnx`).

PREPROCESSING CONTRACT — this is the SERVE side of the three-file contract:
    frontend/src/lib/preprocess.ts            (browser, produces the tensor)
    affectlearn-ml/training/facial/preprocess.py  (training, MediaPipe cropper)
    THIS file                                 (server inference)

The browser already cropped + normalised each frame (MediaPipe blaze_face_short_range
bbox, 96x96, RGB, /255 then ImageNet mean/std, CHW). The wire payload `frames_b64`
is base64 of a contiguous float32 buffer of shape (frames_captured, 3, 96, 96).
The server therefore does **no** cropping/normalisation — it only:
    1. base64-decode -> float32 -> reshape (frames_captured, 3, 96, 96)
    2. select FRAMES_PER_WINDOW (16) evenly-spaced frames (matches training sampling)
    3. run the ONNX model -> softmax -> engagement level 0..3

Changing crop size / channels / normalisation here is a coordinated change with the
two files above. Do not edit unilaterally.
"""

from __future__ import annotations

import base64
import os
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# ── contract constants (must match preprocess.ts PREPROCESS_CONTRACT) ──────────
INPUT_SIZE = 96
CHANNELS = 3
FRAMES_PER_WINDOW = 16                       # framesPerInferenceWindow
FLOATS_PER_FRAME = CHANNELS * INPUT_SIZE * INPUT_SIZE          # 27_648
BYTES_PER_FRAME = FLOATS_PER_FRAME * 4                          # 110_592

# DAiSEE engagement ordinal classes 0..3
CLASS_LABELS = ("very_low", "low", "high", "very_high")

# ONNX export used input name "clip", output name "logits" (1, T, 3, 96, 96) -> (1, 4)
_ONNX_INPUT = "clip"
_DEFAULT_MODEL_PATH = os.getenv("AFFECT_MODEL_PATH", "models/cnn_lstm_best.onnx")


def decode_frames(frames_b64: str, frames_captured: int) -> np.ndarray | None:
    """Decode the base64 float32 buffer into (frames_captured, 3, 96, 96).

    Returns None when the cycle carried no frames (empty payload). Raises
    ValueError if the byte length does not match `frames_captured` frames —
    that signals a contract violation, not an empty cycle.
    """
    if frames_captured <= 0 or not frames_b64:
        return None

    raw = base64.b64decode(frames_b64)
    expected = frames_captured * BYTES_PER_FRAME
    if len(raw) != expected:
        raise ValueError(
            f"facial_features payload size mismatch: got {len(raw)} bytes, "
            f"expected {expected} ({frames_captured} x {BYTES_PER_FRAME})"
        )

    arr = np.frombuffer(raw, dtype=np.float32)
    return arr.reshape(frames_captured, CHANNELS, INPUT_SIZE, INPUT_SIZE)


def select_window(frames: np.ndarray, n: int = FRAMES_PER_WINDOW) -> np.ndarray:
    """Pick `n` evenly-spaced frames, matching training's `np.linspace` sampling.

    When fewer than `n` frames are present, indices repeat (linspace clamps),
    which pads the window by duplicating frames rather than failing.
    """
    t = frames.shape[0]
    idx = np.linspace(0, max(t - 1, 0), n, dtype=int)
    return frames[idx]


def _softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - logits.max()
    e = np.exp(z)
    return e / e.sum()


class EngagementModel:
    """Lazily-loaded ONNX engagement classifier (process-wide singleton via `get_model`)."""

    def __init__(self, model_path: str = _DEFAULT_MODEL_PATH, session: Any | None = None):
        self.model_path = model_path
        self._session = session  # injectable for tests

    @property
    def session(self):
        if self._session is None:
            import onnxruntime as ort  # imported lazily so the module imports without ORT

            if not os.path.exists(self.model_path):
                raise FileNotFoundError(
                    f"engagement model not found at {self.model_path}; set AFFECT_MODEL_PATH "
                    "or place cnn_lstm_best.onnx there (it lives on Drive, gitignored)."
                )
            self._session = ort.InferenceSession(
                self.model_path, providers=["CPUExecutionProvider"]
            )
            logger.info("engagement_model_loaded", path=self.model_path)
        return self._session

    def infer(self, window: np.ndarray) -> dict[str, Any]:
        """Run one (FRAMES_PER_WINDOW, 3, 96, 96) window. Returns level/label/probs."""
        batch = window[np.newaxis].astype(np.float32)        # (1, T, 3, 96, 96)
        logits = np.asarray(self.session.run(None, {_ONNX_INPUT: batch})[0])[0]
        probs = _softmax(logits)
        level = int(probs.argmax())
        return {
            "engagement_level": level,
            "label": CLASS_LABELS[level],
            "confidence": float(probs[level]),
            "probs": [float(p) for p in probs],
        }


_MODEL: EngagementModel | None = None


def get_model() -> EngagementModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = EngagementModel()
    return _MODEL


def predict_from_payload(
    frames_b64: str, frames_captured: int, model: EngagementModel | None = None
) -> dict[str, Any] | None:
    """End-to-end: decode -> select 16 -> infer. Returns None for an empty cycle.

    On an empty cycle (no detected face all 30s) the caller should fall back to
    behavioural-only weighting for that cycle (architecture decision).
    """
    frames = decode_frames(frames_b64, frames_captured)
    if frames is None or frames.shape[0] == 0:
        return None
    window = select_window(frames)
    result = (model or get_model()).infer(window)
    result["frames_used"] = int(min(frames.shape[0], FRAMES_PER_WINDOW))
    return result
