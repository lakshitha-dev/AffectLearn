"""Behavioral affect inference service (Story 4.4b).

Consumes the `behavioral_window` WebSocket payload (Story 4.3 raw timed events) and runs
the Bi-LSTM behavioral affect model exported to ONNX (`behavioral_bilstm.onnx`).

Pipeline (train/serve parity — ml-training-guide-behavioral.md §7):
    1. adapt Story 4.3 `BehavioralEvent[]` -> the extractor's raw-event DataFrame
    2. `feature_engineering.extract_features` -> (30, 13) float32  (ported verbatim)
    3. global z-score normalize with `behavioral_feature_stats.json` (mean/std per feature)
    4. ONNX `window (1,30,13)` -> `logits (1,4)` -> softmax -> argmax class

The Bi-LSTM emits ALL FOUR affect categories natively (its own class order — see
`BEHAVIORAL_CLASS_ORDER`, which DIFFERS from the facial `AFFECT_CLASS_ORDER`), so there
is no engagement stand-in adapter here. The model is currently trained on SYNTHETIC
Phase-A-like data (demo-grade ~50-65%); it is a swappable artifact (`BEHAVIORAL_MODEL_PATH`)
replaced by a real-pilot-trained model with no backend change.

The model loads lazily as a process-wide singleton (mirrors `model_inference.get_model`);
the injectable `session` seam lets tests run without the ONNX artifact.
"""

from __future__ import annotations

import json
import os
from typing import Any

import numpy as np
import structlog

from app.services.feature_engineering import N_FEATURES, extract_features

logger = structlog.get_logger(__name__)

# Class index -> label, from affectlearn-ml/training/behavioral/config.yaml:
#   labels: [Engaged, Bored, Confused, Frustrated]
# NOTE: this order DIFFERS from the facial AFFECT_CLASS_ORDER — do not reuse that constant.
BEHAVIORAL_CLASS_ORDER: tuple[str, ...] = ("engaged", "bored", "confused", "frustrated")

WINDOW_LENGTH_MS = 30_000
_ONNX_INPUT = "window"  # verified via onnxruntime: input "window" (B,30,13) -> "logits" (B,4)

_DEFAULT_MODEL_PATH = os.getenv("BEHAVIORAL_MODEL_PATH", "models/behavioral_bilstm.onnx")
_DEFAULT_STATS_PATH = os.getenv("BEHAVIORAL_STATS_PATH", "models/behavioral_feature_stats.json")

# Nominal viewport for normalizing mouse coords to [0,1] (Story 4.3 sends CSS pixels and
# no viewport dims). Documented stopgap — Open Question #1.
_VIEWPORT_W = float(os.getenv("BEHAVIORAL_VIEWPORT_W", "1920"))
_VIEWPORT_H = float(os.getenv("BEHAVIORAL_VIEWPORT_H", "1080"))


def _softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - logits.max()
    e = np.exp(z)
    return e / e.sum()


def _events_to_dataframe(
    events: list[dict[str, Any]],
    capture_started_at_wall: int,
    window_length_ms: int = WINDOW_LENGTH_MS,
):
    """Adapt Story 4.3 `BehavioralEvent[]` to the extractor's raw-event DataFrame.

    Columns: ts (window-relative ms), type, x, y, key, dy. `ts = t_wall - window_start`,
    clamped to [0, window_length_ms). Mouse coords are normalized to [0,1] by a nominal
    viewport. Keystroke content is never read — only `category == "backspace"` maps to the
    `"Backspace"` key the extractor's `backspace_pct` tests. Visibility events are dropped.
    """
    import pandas as pd

    rows: list[tuple] = []
    start = int(capture_started_at_wall or 0)
    if not start and events:
        # Defensive (M1): real t_wall is Date.now() (~1.7e12). If the window start is
        # missing/0, `ts = t_wall - 0` would exceed the window and silently drop EVERY
        # event into an idle zero-window. Anchor to the earliest event instead + warn.
        first = min((int(e["t_wall"]) for e in events if e.get("t_wall") is not None), default=0)
        start = first
        logger.warning("behavioral_window_start_missing", anchored_to=start)
    for e in events or []:
        t_wall = e.get("t_wall")
        if t_wall is None:
            continue
        ts = int(t_wall) - start
        if ts < 0 or ts >= window_length_ms:
            continue
        kind = e.get("kind")
        if kind == "mouse_sample":
            x = min(max(float(e.get("x", 0.0) or 0.0) / _VIEWPORT_W, 0.0), 1.0)
            y = min(max(float(e.get("y", 0.0) or 0.0) / _VIEWPORT_H, 0.0), 1.0)
            rows.append((ts, "move", x, y, "", 0.0))
        elif kind == "mouse_click":
            rows.append((ts, "click", 0.0, 0.0, "", 0.0))
        elif kind == "key":
            key = "Backspace" if e.get("category") == "backspace" else ""
            rows.append((ts, "key", 0.0, 0.0, key, 0.0))
        elif kind == "scroll":
            rows.append((ts, "scroll", 0.0, 0.0, "", float(e.get("delta_y", 0.0) or 0.0)))
        # visibility (and any unknown kind) -> dropped; the extractor doesn't use them
    return pd.DataFrame(rows, columns=["ts", "type", "x", "y", "key", "dy"])


def _load_stats(path: str) -> dict[str, np.ndarray]:
    """Load global z-score mean/std (per feature). Identity + warn if the file is absent.

    Training used `normalization: global_zscore`; serving MUST apply the same stats or the
    model sees an unnormalized distribution. A missing stats file is a deployment error
    (model and stats ship together) — we warn loudly and fall back to identity rather than
    hard-failing the whole behavioral path.
    """
    if not os.path.exists(path):
        logger.warning("behavioral_stats_missing", path=path)
        return {"mean": np.zeros(N_FEATURES, dtype=np.float32),
                "std": np.ones(N_FEATURES, dtype=np.float32)}
    with open(path) as fh:
        data = json.load(fh)
    return {"mean": np.asarray(data["mean"], dtype=np.float32),
            "std": np.asarray(data["std"], dtype=np.float32)}


class BehavioralModel:
    """Lazily-loaded ONNX Bi-LSTM (process-wide singleton via `get_behavioral_model`)."""

    def __init__(
        self,
        model_path: str = _DEFAULT_MODEL_PATH,
        stats_path: str = _DEFAULT_STATS_PATH,
        session: Any | None = None,
        stats: dict[str, np.ndarray] | None = None,
    ):
        self.model_path = model_path
        self.stats_path = stats_path
        self._session = session  # injectable for tests
        self._stats = stats       # injectable for tests

    @property
    def session(self):
        if self._session is None:
            import onnxruntime as ort  # imported lazily so the module imports without ORT

            if not os.path.exists(self.model_path):
                raise FileNotFoundError(
                    f"behavioral model not found at {self.model_path}; set BEHAVIORAL_MODEL_PATH "
                    "or place behavioral_bilstm.onnx there (it lives on Drive, gitignored)."
                )
            self._session = ort.InferenceSession(
                self.model_path, providers=["CPUExecutionProvider"]
            )
            logger.info("behavioral_model_loaded", path=self.model_path)
        return self._session

    @property
    def stats(self) -> dict[str, np.ndarray]:
        if self._stats is None:
            self._stats = _load_stats(self.stats_path)
        return self._stats

    def _normalize(self, features: np.ndarray) -> np.ndarray:
        mean = self.stats["mean"]
        std = self.stats["std"]
        safe_std = np.where(std == 0, 1.0, std)  # guard zero-variance features
        return (features - mean) / safe_std

    def infer(self, features: np.ndarray) -> dict[str, Any]:
        """Run one (30, N_FEATURES) feature window. Returns affect_index/label/probs."""
        norm = self._normalize(features).astype(np.float32)
        batch = norm[np.newaxis]                              # (1, 30, 13)
        logits = np.asarray(self.session.run(None, {_ONNX_INPUT: batch})[0])[0]
        probs = _softmax(logits)
        idx = int(probs.argmax())
        return {
            "affect_index": idx,
            "label": BEHAVIORAL_CLASS_ORDER[idx],
            "confidence": float(probs[idx]),
            "probs": [float(p) for p in probs],
        }


_MODEL: BehavioralModel | None = None


def get_behavioral_model() -> BehavioralModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = BehavioralModel()
    return _MODEL


def predict_from_window(
    events: list[dict[str, Any]],
    capture_started_at_wall: int,
    model: BehavioralModel | None = None,
) -> dict[str, Any] | None:
    """End-to-end: adapt events -> extract (30,13) -> normalize -> infer.

    An idle window (no events) yields an all-zeros feature window which the model still
    classifies (a valid low-activity input) — this does NOT return None. None is reserved
    for a structurally unusable window (none currently arise; kept for forward-compat).
    """
    df = _events_to_dataframe(events or [], capture_started_at_wall)
    features = extract_features(df, window_start=0, window_length_ms=WINDOW_LENGTH_MS)
    result = (model or get_behavioral_model()).infer(features)
    result["n_bins"] = int(features.shape[0])
    return result
