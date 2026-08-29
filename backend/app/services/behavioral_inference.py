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

from app.services import onnx_session

from app.services.feature_engineering import (
    FEATURE_SCHEMA_VERSION,
    N_FEATURES,
    extract_features,
)

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

    prev_scroll_y: float | None = None
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
            # `delta_y` is the wheel delta and is 0 for NATIVE scrolls (keyboard, trackbar,
            # scrollbar drag, programmatic). Using it alone made every non-wheel scroll invisible
            # to `scroll_velocity_mean` and `scroll_back_runs` — a large blind spot on a reading
            # platform. Fall back to the change in absolute `scroll_y`, which is always present.
            delta = float(e.get("delta_y", 0.0) or 0.0)
            scroll_y = e.get("scroll_y")
            if scroll_y is not None:
                y_now = float(scroll_y)
                if delta == 0.0 and prev_scroll_y is not None:
                    delta = y_now - prev_scroll_y
                prev_scroll_y = y_now
            rows.append((ts, "scroll", 0.0, 0.0, "", delta))
        elif kind == "visibility":
            # `dy` carries the STATE, not a delta: 1.0 hidden, 0.0 visible. Consumed by
            # `_blur_per_bin`, which integrates it across bins. Previously dropped here, which
            # discarded a signal the frontend had been collecting since Story 4.3.
            hidden = 1.0 if str(e.get("state", "")).lower() == "hidden" else 0.0
            rows.append((ts, "visibility", 0.0, 0.0, "", hidden))
        # any unknown kind -> dropped
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
        self._kind_cache: str | None = None

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
                self.model_path,
                sess_options=onnx_session.session_options(ort),
                providers=["CPUExecutionProvider"],
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

    def _kind(self) -> str:
        """Which artifact is loaded: the sequence Bi-LSTM or the aggregate-feature GBDT.

        Detected from the ONNX signature rather than an env flag, so the artifact and the code path
        cannot disagree:
            (B, 30, 16) -> "sequence"     the Bi-LSTM (4 logits over BEHAVIORAL_CLASS_ORDER)
            (B, 80)     -> "aggregate"    the DUX-trained confusion GBDT (2 probabilities)
        Anything unrecognised falls back to "sequence", preserving the historic behaviour and the
        test doubles that report no shape at all.
        """
        if self._kind_cache is None:
            self._kind_cache = "sequence"
            try:
                shape = self.session.get_inputs()[0].shape
                if len(shape) == 2:
                    self._kind_cache = "aggregate"
            except Exception:
                pass
        return self._kind_cache

    def _infer_aggregate(self, features: np.ndarray) -> dict[str, Any]:
        """DUX-trained GBDT: (n_bins, 16) -> aggregate -> P(confused).

        NO z-normalisation here. The Bi-LSTM path z-scores because a neural net needs it; the GBDT
        was fitted on RAW aggregate features and applying the Bi-LSTM's stats would silently shift
        every input away from what the trees split on.

        The 4-slot `probs` contract is preserved so nothing downstream changes, but only two slots
        can ever be non-zero: this model detects confusion and nothing else. Bored and frustrated
        stay at 0.0 exactly as the facial engagement stand-in does in `agents/fusion.py` — a channel
        that cannot see a state must not vote on it. `engaged` carries 1 - P(confused) and is the
        do-nothing state the adaptation gate already excludes from `ADAPT_STATES`.
        """
        from app.services.aggregate_features import aggregate

        agg = aggregate(features[np.newaxis]).astype(np.float32)   # (1, 80)
        name = self.session.get_inputs()[0].name
        outputs = self.session.run(None, {name: agg})
        # skl2onnx emits [label, probabilities]; take the probability tensor whichever slot it is.
        prob_arr = None
        for o in outputs:
            arr = np.asarray(o)
            if arr.ndim == 2 and arr.shape[-1] == 2:
                prob_arr = arr
                break
        if prob_arr is None:
            raise ValueError(
                f"{self.model_path} did not return a (N,2) probability tensor; got shapes "
                f"{[np.asarray(o).shape for o in outputs]}"
            )
        p_confused = float(prob_arr[0, 1])

        probs = [0.0] * len(BEHAVIORAL_CLASS_ORDER)
        probs[BEHAVIORAL_CLASS_ORDER.index("confused")] = p_confused
        probs[BEHAVIORAL_CLASS_ORDER.index("engaged")] = 1.0 - p_confused
        idx = int(np.argmax(probs))
        return {
            "affect_index": idx,
            "label": BEHAVIORAL_CLASS_ORDER[idx],
            "confidence": float(probs[idx]),
            "probs": probs,
            "model_kind": "aggregate_confusion_gbdt",
            "p_confused": p_confused,
        }

    def infer(self, features: np.ndarray) -> dict[str, Any]:
        """Run one (n_bins, N_FEATURES) feature window. Returns affect_index/label/probs."""
        if self._kind() == "aggregate":
            return self._infer_aggregate(features)
        # Fail with a diagnosis, not an onnxruntime shape error. The extractor and the exported
        # model must agree on width, and they only do if the model was retrained AFTER the last
        # feature-schema change — the deploy order is features -> retrain -> redeploy, together.
        #
        # Best-effort by design: this is a diagnostic, so a session that cannot report its input
        # shape (a test double, a future runtime) must fall through to normal inference rather
        # than be blocked by the check meant to help.
        want = None
        try:
            shape = self.session.get_inputs()[0].shape
            if isinstance(shape[-1], int):
                want = shape[-1]
        except Exception:
            want = None
        if want is not None and features.shape[-1] != want:
            raise ValueError(
                f"feature width mismatch: extractor produces {features.shape[-1]} features "
                f"(schema v{FEATURE_SCHEMA_VERSION}, {N_FEATURES} names) but "
                f"{self.model_path} expects {want}. Retrain and re-export the model — the "
                "deployed ONNX predates the current feature schema."
            )
        norm = self._normalize(features).astype(np.float32)
        batch = norm[np.newaxis]                              # (1, n_bins, N_FEATURES)
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


def extract_window_features(
    events: list[dict[str, Any]],
    capture_started_at_wall: int | None,
) -> dict[str, Any]:
    """Adapt events and extract the aggregate feature window — WITHOUT running the model.

    Split out from `predict_from_window` so a window's features can still be persisted when
    inference fails. The raw events are transient (dropped at the end of the cycle), so without
    this a missing or stale ONNX file would silently destroy every window of a collection
    session. Extraction depends on nothing but pandas/numpy.
    """
    df = _events_to_dataframe(events or [], capture_started_at_wall or 0)
    features = extract_features(df, window_start=0, window_length_ms=WINDOW_LENGTH_MS)
    return {
        "features": features.round(6).tolist(),
        "n_bins": int(features.shape[0]),
        "n_features": int(features.shape[1]),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
    }


def predict_from_window(
    events: list[dict[str, Any]],
    capture_started_at_wall: int,
    model: BehavioralModel | None = None,
) -> dict[str, Any] | None:
    """End-to-end: adapt events -> extract (n_bins, N_FEATURES) -> normalize -> infer.

    An idle window (no events) yields an all-zeros feature window which the model still
    classifies (a valid low-activity input) — this does NOT return None. None is reserved
    for a structurally unusable window (none currently arise; kept for forward-compat).
    """
    df = _events_to_dataframe(events or [], capture_started_at_wall)
    features = extract_features(df, window_start=0, window_length_ms=WINDOW_LENGTH_MS)
    result = (model or get_behavioral_model()).infer(features)
    result["n_bins"] = int(features.shape[0])
    # Persist the RAW (pre-normalisation) aggregate feature window so Phase A data is
    # trainable. These are aggregate statistics (entropy, velocities, counts) — NOT raw
    # events — so this honours NFR10 / the consent's "only aggregate features". Training
    # fits its own z-score, so we store the un-normalised window: the exact (n_bins,
    # N_FEATURES) array infer() consumed, guaranteeing train/serve parity (guide §7).
    result["features"] = features.round(6).tolist()   # (n_bins, N_FEATURES)
    # Stamped so a training set can never silently mix windows from two feature schemas.
    result["feature_schema_version"] = FEATURE_SCHEMA_VERSION
    return result
