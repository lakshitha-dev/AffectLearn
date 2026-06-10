"""Multimodal late fusion + ablation forcing (Story 4.4c — FR13, FR14).

LATE FUSION (result-level). Raw frames are transient (NFR10) and cannot be re-inferred
when the counterpart modality arrives, so fusion combines the cached probability OUTPUTS
of the facial (Story 4.4) and behavioral (Story 4.4b) models — true "late fusion"
(architecture.md line 190). This module is PURE (no I/O beyond an env read) and unit-
testable without ONNX.

CANONICAL ORDER. The two models speak different label spaces, so both are projected into
`CANONICAL_ORDER = AFFECT_STATES = (bored, confused, engaged, frustrated)` before fusing:
  * behavioral: probs over BEHAVIORAL_CLASS_ORDER (engaged, bored, confused, frustrated)
    -> reordered into canonical.
  * facial engagement stand-in: probs over [very_low, low, high, very_high] -> mass on
    `bored` (low+very_low) and `engaged` (high+very_high) only; it CANNOT see confused /
    frustrated (Story 4.4 honesty flag). A true 4-category facial model maps directly.

FUSION RULE. Confidence-weighted average: `(wf·cf + wb·cb) / (wf + wb)`, so the higher-
confidence modality dominates (epic AC line 818). A learned fusion layer (ML repo
`fusion/train_fusion.py`) can later replace the weights with no interface change.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np
import structlog

from app.agents.state import AFFECT_SOURCE_FUSION, AFFECT_STATES
from app.services.behavioral_inference import BEHAVIORAL_CLASS_ORDER

logger = structlog.get_logger(__name__)

CANONICAL_ORDER: tuple[str, ...] = AFFECT_STATES  # (bored, confused, engaged, frustrated)
FUSION_PAIR_WINDOW_MS = int(os.getenv("FUSION_PAIR_WINDOW_MS", "20000"))

_VALID_MODES = ("auto", "facial_only", "behavioral_only", "multimodal")


def forced_mode() -> str:
    """Ablation control (FR14). `AFFECT_DETECTION_MODE` env; default `auto`."""
    mode = os.getenv("AFFECT_DETECTION_MODE", "auto").strip().lower()
    if mode not in _VALID_MODES:
        logger.warning("invalid_forced_mode", value=mode)
        return "auto"
    return mode


def behavioral_to_canonical(probs: list[float]) -> np.ndarray:
    """Reorder behavioral probs (BEHAVIORAL_CLASS_ORDER) into CANONICAL_ORDER."""
    pos = {label: i for i, label in enumerate(BEHAVIORAL_CLASS_ORDER)}
    return np.array([float(probs[pos[c]]) for c in CANONICAL_ORDER], dtype=float)


def facial_to_canonical(facial_result: dict[str, Any], kind: str | None = None) -> np.ndarray:
    """Project a facial inference result into CANONICAL_ORDER.

    category model: probs already in AFFECT_CLASS_ORDER == canonical -> passthrough.
    engagement stand-in: [very_low, low, high, very_high] -> bored=p0+p1, engaged=p2+p3,
    confused=frustrated=0 (the stand-in has no signal there).
    """
    probs = facial_result.get("probs") or []
    if kind is None:
        from app.agents.affect_mapping import _model_kind
        kind = _model_kind()
    if kind == "category":
        return np.array([float(p) for p in probs], dtype=float)
    if len(probs) < 4:
        return np.zeros(len(CANONICAL_ORDER), dtype=float)
    bored = float(probs[0]) + float(probs[1])      # very_low + low
    engaged = float(probs[2]) + float(probs[3])    # high + very_high
    # CANONICAL_ORDER = (bored, confused, engaged, frustrated)
    return np.array([bored, 0.0, engaged, 0.0], dtype=float)


def _normalize(v: np.ndarray) -> np.ndarray:
    s = v.sum()
    return v / s if s > 0 else v


def fuse_modalities(
    facial_result: dict[str, Any] | None = None,
    behavioral_result: dict[str, Any] | None = None,
    facial_kind: str | None = None,
) -> dict[str, Any]:
    """Confidence-weighted late fusion of two unimodal results into one estimate.

    Degrades to the single present modality if the other is missing; never raises. Returns
    the fused affect_state (canonical argmax), fused confidence, both unimodal confidences,
    and the fusion weights — the unimodal confidences/weights drive ablation analysis.
    """
    wf = float(facial_result.get("confidence", 0.0)) if facial_result else 0.0
    wb = float(behavioral_result.get("confidence", 0.0)) if behavioral_result else 0.0
    n = len(CANONICAL_ORDER)
    cf = _normalize(facial_to_canonical(facial_result, facial_kind)) if facial_result else np.zeros(n)
    cb = _normalize(behavioral_to_canonical(behavioral_result["probs"])) if behavioral_result else np.zeros(n)

    denom = wf + wb
    if denom > 0:
        fused = (wf * cf + wb * cb) / denom
        weights = {"facial": wf / denom, "behavioral": wb / denom}
    else:
        # both zero-confidence: equal weight over whichever modalities are present
        mats = []
        if facial_result:
            mats.append(cf)
        if behavioral_result:
            mats.append(cb)
        fused = sum(mats) / len(mats) if mats else np.zeros(n)
        weights = {"facial": 0.0, "behavioral": 0.0}

    idx = int(np.argmax(fused)) if fused.sum() > 0 else 0
    return {
        "affect_state": CANONICAL_ORDER[idx],
        "affect_confidence": float(fused[idx]),
        "fused_probs": [float(x) for x in fused],
        "facial_confidence": wf,
        "behavioral_confidence": wb,
        "weights": weights,
        "affect_source": AFFECT_SOURCE_FUSION,
    }
