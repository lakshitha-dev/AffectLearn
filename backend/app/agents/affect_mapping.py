"""Resolve a model inference result into one of the 4 affect CATEGORIES (Story 4.4).

The system's contract (FR13, architecture line 583, the self-report ground truth,
the designer heatmap, FYRP RQ1) is that affect is one of:
    bored | confused | engaged | frustrated

The facial model artifact may be either:
  * a true 4-category model  (AFFECT_MODEL_KIND="category")  — its class indices map
    directly to AFFECT_CLASS_ORDER; or
  * the current engagement stand-in (AFFECT_MODEL_KIND="engagement", the default)
    which emits DAiSEE engagement intensity (very_low/low/high/very_high). Until the
    facial model is RETRAINED to emit the 4 categories (tracked ML-repo dependency),
    `engagement_to_affect` is a STOPGAP that collapses intensity into engaged/bored.

`confused` and `frustrated` are NOT recoverable from an engagement-only model — they
arrive with the retrained category model, the behavioral Bi-LSTM (Story 4.4b), and
fusion (Story 4.4c). Every cycle records `affect_source` so research data is explicit
about how each label was produced. This module is pure (no I/O beyond an env read) so
it is unit-testable without ONNX.
"""

from __future__ import annotations

import os
from typing import Any

from app.agents.state import (
    AFFECT_SOURCE_CATEGORY,
    AFFECT_SOURCE_ENGAGEMENT,
)

# The class order a retrained 4-category facial model MUST output (index -> label).
# Documented here so the ML re-export and this adapter stay in lockstep.
AFFECT_CLASS_ORDER: tuple[str, ...] = ("bored", "confused", "engaged", "frustrated")


def index_to_affect(index: int) -> str:
    """Map a 4-category model's class index directly to an affect label."""
    if 0 <= index < len(AFFECT_CLASS_ORDER):
        return AFFECT_CLASS_ORDER[index]
    return "bored"  # defensive default for an out-of-range index


def engagement_to_affect(level: int) -> str:
    """STOPGAP: collapse DAiSEE engagement intensity (0..3) into an affect category.

    very_high(3)/high(2) -> engaged ;  low(1)/very_low(0) -> bored.

    This is a deliberately conservative 2-way collapse used ONLY while the engagement
    stand-in model is loaded. It cannot produce `confused`/`frustrated`. Remove once
    the retrained 4-category facial model lands (set AFFECT_MODEL_KIND=category).
    Out-of-range input defaults to `bored`.
    """
    if level >= 2:
        return "engaged"
    return "bored"


#: Index of the positive class in the binary confusion facial artifact
#: (`cnn_lstm_confusion_anycut.onnx`, logits over [not_confused, confused]).
BINARY_CONFUSED_INDEX = 1


def binary_confusion_to_affect(index: int) -> str:
    """Map the binary confusion model's class index to an affect category.

    1 -> confused ; 0 -> engaged (the do-nothing state, which `ADAPT_STATES` excludes).

    "engaged" is the honest reading of the negative class here, not a detection of
    engagement: the model was trained on DAiSEE's Confusion dimension under the ANY cut,
    so class 0 means "no confusion annotated", nothing more. It is mapped to engaged
    rather than bored because bored is an ACTIONABLE state the model cannot see, and
    routing a negative into an actionable state would fire interventions on absence of
    evidence. Engagement itself is separately unusable on DAiSEE (4 disengaged clips in
    1638 test clips), which is why this artifact targets confusion at all.
    """
    return "confused" if index == BINARY_CONFUSED_INDEX else "engaged"


def _model_kind() -> str:
    """Which facial artifact is loaded. Mirrors model_inference's os.getenv pattern.

        engagement (default) DAiSEE engagement stand-in, 4 intensity levels
        category             a true 4-category model, indices map to AFFECT_CLASS_ORDER
        binary_confusion     cnn_lstm_confusion_anycut.onnx, 2 logits, AUC 0.6414 on the
                             DAiSEE test split (kappa 0.2119, n=1638)
    """
    return os.getenv("AFFECT_MODEL_KIND", "engagement").strip().lower()


# Which engagement intensity levels collapse into each affect category under the
# engagement stand-in adapter. Used to AGGREGATE softmax mass when scoring the chosen
# category's confidence (a 2-way collapse means the category's confidence is the SUM
# of its levels' probabilities, not the single argmax prob). Keep in lockstep with
# `engagement_to_affect`.
_ENGAGEMENT_LEVELS_FOR: dict[str, tuple[int, ...]] = {
    "engaged": (2, 3),   # high, very_high
    "bored": (0, 1),     # low, very_low
}


def category_confidence(inference: dict[str, Any], affect_state: str, kind: str) -> float:
    """Confidence in the CHOSEN affect category.

    category model: the chosen class is a single index, so its own softmax prob IS the
    confidence (`inference["confidence"]`).
    engagement adapter: the category aggregates >1 engagement level, so confidence is
    the SUM of those levels' probabilities. Using the single argmax prob here would
    systematically UNDERSTATE confidence in the collapsed category (AC3 — "softmax
    confidence for the chosen class"). Falls back to the raw confidence when `probs`
    is absent.
    """
    raw = float(inference.get("confidence", 0.0))
    probs = inference.get("probs")
    if kind == "category" or not probs:
        return raw
    levels = _ENGAGEMENT_LEVELS_FOR.get(affect_state)
    if not levels:
        return raw
    return float(sum(probs[i] for i in levels if 0 <= i < len(probs)))


def _positive_prob(inference: dict[str, Any]) -> float:
    """P(confused) from a binary artifact, independent of which class won the argmax.

    Recorded on every cycle because the CATEGORY alone is lossy: a window at 0.51 and one at
    0.99 both resolve to `confused`, and only the raw probability lets the gate threshold be
    recalibrated from logged research data later without re-running inference.
    """
    probs = inference.get("probs")
    if probs and len(probs) > BINARY_CONFUSED_INDEX:
        return float(probs[BINARY_CONFUSED_INDEX])
    # No probs vector: recover it from the confidence, which belongs to whichever class won.
    conf = float(inference.get("confidence", 0.0))
    return conf if int(inference.get("engagement_level", 0)) == BINARY_CONFUSED_INDEX else 1.0 - conf


def resolve_affect(
    inference: dict[str, Any], kind: str | None = None
) -> tuple[str, str, float, dict[str, Any]]:
    """Turn an inference result into (affect_state, affect_source, affect_confidence, extra_fields).

    `inference` is the dict from `model_inference.predict_from_payload`
    (`engagement_level`, `label`, `confidence`, `probs`, ...). `engagement_level`
    holds the model's argmax class index in both cases.

    Returns the affect category, the provenance marker, the confidence in the chosen
    CATEGORY (aggregated across collapsed levels under the adapter — see
    `category_confidence`), and any additive fields (engagement_level/engagement_label)
    that should be merged into AgentState — only populated under the engagement adapter.
    """
    kind = (kind or _model_kind())
    index = int(inference["engagement_level"])

    if kind == "category":
        affect = index_to_affect(index)
        return affect, AFFECT_SOURCE_CATEGORY, category_confidence(inference, affect, kind), {}

    if kind == "binary_confusion":
        # Two logits, so the argmax prob IS the confidence — nothing to aggregate. Reported
        # under AFFECT_SOURCE_CATEGORY because, unlike the engagement stand-in, this artifact
        # genuinely predicts an affect category rather than having one inferred from intensity.
        affect = binary_confusion_to_affect(index)
        return (affect, AFFECT_SOURCE_CATEGORY,
                float(inference.get("confidence", 0.0)),
                {"p_confused": _positive_prob(inference)})

    # engagement stand-in (default)
    affect = engagement_to_affect(index)
    extra = {
        "engagement_level": index,
        "engagement_label": inference.get("label"),
    }
    return affect, AFFECT_SOURCE_ENGAGEMENT, category_confidence(inference, affect, kind), extra
