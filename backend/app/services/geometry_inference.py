"""SERVE side of the facial-geometry contract: 11 scalars per frame -> P(disengaged).

THE THREE-FILE CONTRACT

This file is one of three that must agree, exactly as `model_inference.py` is for the pixel path:

    frontend/src/lib/geometry.ts          computes the 11 per-frame scalars in the browser
    training/engagenet/extract_geometry.py  computed them in Python at training time
    this file                              aggregates them and runs the model

A drift between any two silently feeds the model features it was never trained on, and the model
will keep returning confident numbers. This project has already paid for that once: the pixel path
trained at 1.93 s frame spacing while serving at 0.67 s, with nothing checking the correspondence.
`backend/tests/services/test_geometry_parity.py` is the control — golden vectors frozen from the
Python extractor that the TypeScript implementation must reproduce.

WHY GEOMETRY RATHER THAN PIXELS

The model consumes ~600 bytes per cycle instead of ~4.4 MB of base64 face crops, and no image ever
leaves the browser. That is a stronger privacy guarantee than the pixel path can offer under any
transport encryption, and it is what makes the consent copy in `ConsentStep.tsx` true.

WHAT IT PREDICTS, AND WHAT IT DOES NOT

Binary disengagement only: P(low engagement) from EngageNet's behavioural definition of a learner
who frequently glances away. It cannot see `confused` or `frustrated` — those are not annotated in
that corpus, so no amount of retraining on it would produce them. `confused` comes from the
behavioural channel; the two are complementary, not redundant, and are deliberately not fused
(see `fusion.py:facial_to_canonical`).

    AUC 0.9225 on the EngageNet test split, 2,256 clips / 26 held-out participants,
    accuracy 0.8630 against a 0.6884 majority baseline, kappa 0.6877.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# ── the contract, locked ──────────────────────────────────────────────────────────────
#: Per-frame channels in the order `extract_geometry.py` emits them. The browser MUST send
#: this order; index positions below are taken from it rather than from names on the wire.
GEOMETRY_CHANNEL_ORDER: tuple[str, ...] = (
    "yaw", "pitch", "roll", "ear_l", "ear_r", "ear_mean",
    "mouth_open", "gaze_x", "gaze_y", "motion", "face_found",
)

#: The four channels the deployed model actually consumes (`4_lean`). Head pose and eye-aspect
#: ratio are deliberately absent: on EngageNet, removing head pose RAISED AUC by 0.023, and the
#: eye channels were neutral. The browser still sends all eleven so the discarded ones can be
#: logged for research and a future model can use them without a frontend change.
MODEL_CHANNELS: tuple[str, ...] = ("gaze_x", "gaze_y", "mouth_open", "motion")

#: 10 frames at 1 fps. A train/serve parity term, not a tuning choice.
EXPECTED_FRAMES = 10
CAPTURE_FPS = 1.0

#: Aggregation applied per channel, in this order. 20 features = 4 channels x 5 statistics.
STAT_ORDER: tuple[str, ...] = ("mean", "std", "min", "max", "trend")

FEATURE_NAMES: tuple[str, ...] = tuple(
    f"{stat}_{ch}" for stat in STAT_ORDER for ch in MODEL_CHANNELS
)
N_FEATURES = len(FEATURE_NAMES)  # 20

#: Class order of the ONNX output. Index 1 is the positive (disengaged) class.
GEOMETRY_CLASS_ORDER: tuple[str, ...] = ("engaged", "disengaged")

_MODEL_PATH = os.getenv("GEOMETRY_MODEL_PATH", "models/engagenet_lean_gbdt.onnx")
_session = None


def _get_session():
    """Lazy ONNX session, mirroring model_inference's pattern so startup cost is not paid twice."""
    global _session
    if _session is None:
        import onnxruntime as ort
        _session = ort.InferenceSession(_MODEL_PATH, providers=["CPUExecutionProvider"])
        logger.info("geometry_model_loaded", path=_MODEL_PATH,
                    inputs=[i.name for i in _session.get_inputs()])
    return _session


def five_stats(seq: np.ndarray) -> np.ndarray:
    """mean/std/min/max/trend per channel — a direct port of `rungs.five_stats`.

    `trend` is late-third mean minus early-third mean, which is the only one of the five that
    carries direction: it separates a learner drifting away over the window from one who was away
    throughout. The `max(1, ...)` guard matters at this window length — with 10 frames the third
    is 3, and a shorter window must not produce an empty slice.

    NaN-aware throughout, because a frame with no detected face contributes NaN rather than zero;
    treating those as zero would place a "looking dead ahead" reading where there is no reading.
    """
    if seq.shape[0] == 0:
        return np.zeros(seq.shape[1] * len(STAT_ORDER), dtype=np.float64)
    third = max(1, seq.shape[0] // 3)
    early = np.nanmean(seq[:third], axis=0)
    late = np.nanmean(seq[-third:], axis=0)
    return np.concatenate([
        np.nanmean(seq, axis=0), np.nanstd(seq, axis=0),
        np.nanmin(seq, axis=0), np.nanmax(seq, axis=0), late - early,
    ])


def build_features(frames: list[list[float]]) -> np.ndarray:
    """(n_frames, 11) per-frame geometry -> (1, 20) model input.

    Raises on a channel-count mismatch rather than padding: a short row means the browser and this
    file disagree about the contract, and silently zero-filling would hand the model a plausible
    vector built from the wrong columns.
    """
    arr = np.asarray(frames, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != len(GEOMETRY_CHANNEL_ORDER):
        raise ValueError(
            f"expected (n_frames, {len(GEOMETRY_CHANNEL_ORDER)}) geometry, got {arr.shape}. "
            f"Channel order is {GEOMETRY_CHANNEL_ORDER}."
        )
    idx = [GEOMETRY_CHANNEL_ORDER.index(c) for c in MODEL_CHANNELS]
    with np.errstate(invalid="ignore"):
        feats = five_stats(arr[:, idx])
    # An all-NaN channel (no face in any frame) yields NaN, which ONNX will not accept. Zero is
    # the value the training pipeline also substituted at this point, so this matches, and the
    # face_found channel below is what actually carries "there was nobody there".
    return np.nan_to_num(feats, nan=0.0, posinf=0.0, neginf=0.0).reshape(1, -1).astype(np.float32)


def predict_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Run the geometry model over one cycle's payload.

    Returns None for a cycle with nothing to score — no frames, or no face in any frame. That is
    the same empty-chair guard the pixel path applies (`affect_detection.py:31-67`), and it is the
    reason `face_found` is transmitted even though the model does not consume it: an absent
    learner must produce no affect reading at all, rather than a confident one built from a
    centre-crop of an empty chair.
    """
    frames = payload.get("geometry") or []
    if not frames:
        return None

    arr = np.asarray(frames, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != len(GEOMETRY_CHANNEL_ORDER):
        logger.warning("geometry_contract_mismatch", shape=list(arr.shape),
                       expected_channels=len(GEOMETRY_CHANNEL_ORDER))
        return None

    found_idx = GEOMETRY_CHANNEL_ORDER.index("face_found")
    face_ratio = float(np.nan_to_num(arr[:, found_idx]).mean())
    if face_ratio <= 0.0:
        logger.info("geometry_no_face_in_cycle", frames=int(arr.shape[0]))
        return None

    if arr.shape[0] != EXPECTED_FRAMES:
        # Not fatal — a dropped frame still leaves a scoreable window, and five_stats is
        # length-agnostic. Logged because a persistent mismatch is a capture-timing bug, which is
        # exactly the class of defect that went unnoticed on the pixel path.
        logger.warning("geometry_frame_count_mismatch",
                       got=int(arr.shape[0]), expected=EXPECTED_FRAMES)

    x = build_features(frames)
    sess = _get_session()
    outputs = sess.run(None, {sess.get_inputs()[0].name: x})
    # skl2onnx with zipmap=False emits [label, probabilities].
    probs = np.asarray(outputs[1], dtype=float).reshape(-1)
    index = int(np.argmax(probs))
    return {
        "engagement_level": index,                       # key name kept for resolve_affect()
        "label": GEOMETRY_CLASS_ORDER[index],
        "confidence": float(probs[index]),
        "probs": [float(p) for p in probs],
        "face_ratio": face_ratio,
        "frames_scored": int(arr.shape[0]),
    }
