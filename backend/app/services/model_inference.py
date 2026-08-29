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

from app.services import onnx_session

logger = structlog.get_logger(__name__)

# ── contract constants (must match preprocess.ts PREPROCESS_CONTRACT) ──────────
INPUT_SIZE = 96
CHANNELS = 3
FRAMES_PER_WINDOW = 16                       # framesPerInferenceWindow
FLOATS_PER_FRAME = CHANNELS * INPUT_SIZE * INPUT_SIZE          # 27_648
BYTES_PER_FRAME = FLOATS_PER_FRAME * 4                          # 110_592

# Labels depend on WHICH artifact is loaded, so they cannot be a single fixed tuple.
#
# The deployed confusion model has a 2-class head, but this was hardcoded to the 4-level DAiSEE
# engagement vocabulary, so every facial label written to `research_events` came out as
# "very_low"/"low" -- a 2-class argmax indexed into a 4-name list. Prediction was unaffected
# (downstream reads the index and `probs`), but the durable record was garbage.
_LABELS_BY_KIND: dict[str, tuple[str, ...]] = {
    # DAiSEE engagement ordinal classes 0..3
    "engagement": ("very_low", "low", "high", "very_high"),
    # index 1 == confused (see affect_mapping.BINARY_CONFUSED_INDEX)
    "binary_confusion": ("not_confused", "confused"),
    # 4 canonical affect categories, in AFFECT_CLASS_ORDER
    "category": ("bored", "confused", "engaged", "frustrated"),
}

# Retained for backwards compatibility with existing importers; the engagement vocabulary is the
# historical default. Prefer `class_labels()`.
CLASS_LABELS = _LABELS_BY_KIND["engagement"]


def class_labels(kind: str | None = None) -> tuple[str, ...]:
    """Label vocabulary for the resolved adapter kind.

    Resolves the kind from `affect_mapping._model_kind()` (the single source of truth, read from
    env per call) unless one is supplied. Falls back to the engagement vocabulary for an unknown
    kind so this can never raise on a mislabelled deployment.
    """
    if kind is None:
        try:
            from app.agents.affect_mapping import _model_kind

            kind = _model_kind()
        except Exception:  # pragma: no cover - defensive; labels must never break inference
            kind = "engagement"
    return _LABELS_BY_KIND.get(kind, _LABELS_BY_KIND["engagement"])

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
                self.model_path,
                sess_options=onnx_session.session_options(ort),
                providers=["CPUExecutionProvider"],
            )
            logger.info("engagement_model_loaded", path=self.model_path)
        return self._session

    def infer(self, window: np.ndarray) -> dict[str, Any]:
        """Run one (FRAMES_PER_WINDOW, 3, 96, 96) window. Returns level/label/probs."""
        batch = window[np.newaxis].astype(np.float32)        # (1, T, 3, 96, 96)
        logits = np.asarray(self.session.run(None, {_ONNX_INPUT: batch})[0])[0]
        probs = _softmax(logits)
        level = int(probs.argmax())
        labels = class_labels()
        return {
            "engagement_level": level,
            # Guarded index: a kind/artifact mismatch (e.g. `binary_confusion` configured against a
            # 4-class file) must report rather than IndexError mid-cycle.
            "label": labels[level] if level < len(labels) else f"class_{level}",
            "confidence": float(probs[level]),
            "probs": [float(p) for p in probs],
            "model_kind": _resolved_kind(),
            # Only meaningful for a binary confusion head; index 1 == confused.
            "p_confused": float(probs[1]) if len(probs) == 2 else None,
        }


def _resolved_kind() -> str:
    """The adapter kind as the code will interpret this artifact. Never raises."""
    try:
        from app.agents.affect_mapping import _model_kind

        return _model_kind()
    except Exception:  # pragma: no cover - defensive
        return "engagement"


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
