"""The `binary_confusion` facial mode (cnn_lstm_confusion_anycut.onnx, 2 logits).

Why these tests exist: before this artifact, `facial_to_canonical` pinned `confused` at 0.0 under
the engagement stand-in, so the fused confusion estimate came ENTIRELY from the behavioural branch
however "multimodal" the emitted research event claimed to be. These tests pin the property that
makes the facial channel actually participate, and the two properties that keep it honest — bored
and frustrated must stay at zero, because this model cannot see them.
"""

import numpy as np
import pytest

from app.agents.affect_mapping import (
    BINARY_CONFUSED_INDEX,
    binary_confusion_to_affect,
    resolve_affect,
)
from app.agents.fusion import CANONICAL_ORDER, facial_to_canonical, fuse_modalities
from app.agents.state import AFFECT_SOURCE_CATEGORY


def _inference(p_confused: float) -> dict:
    """A facial result in the shape model_inference.predict_from_payload returns."""
    probs = [1.0 - p_confused, p_confused]
    idx = int(np.argmax(probs))
    return {"engagement_level": idx, "label": ["not_confused", "confused"][idx],
            "confidence": float(probs[idx]), "probs": probs}


def test_index_maps_to_confused_or_engaged():
    assert binary_confusion_to_affect(BINARY_CONFUSED_INDEX) == "confused"
    assert binary_confusion_to_affect(0) == "engaged"


def test_negative_class_is_engaged_not_bored():
    """The negative class must not land on an ACTIONABLE state.

    'no confusion annotated' is absence of evidence. Routing it to `bored` — which IS in
    ADAPT_STATES — would fire interventions on absence, which is precisely backwards.
    """
    assert binary_confusion_to_affect(0) == "engaged"
    assert binary_confusion_to_affect(0) != "bored"


def test_resolve_affect_reports_confused_with_its_own_confidence():
    state, source, conf, extra = resolve_affect(_inference(0.82), kind="binary_confusion")
    assert state == "confused"
    assert source == AFFECT_SOURCE_CATEGORY
    assert conf == pytest.approx(0.82)
    assert extra["p_confused"] == pytest.approx(0.82)


def test_p_confused_is_recorded_even_when_not_confused_wins():
    """The category is lossy; 0.49 and 0.01 both resolve to `engaged`.

    Logging the raw probability is what lets the gate threshold be recalibrated from research
    data later without re-running inference over the whole corpus.
    """
    state, _, conf, extra = resolve_affect(_inference(0.49), kind="binary_confusion")
    assert state == "engaged"
    assert conf == pytest.approx(0.51)
    assert extra["p_confused"] == pytest.approx(0.49)


def test_p_confused_recovered_without_a_probs_vector():
    inf = {"engagement_level": 1, "label": "confused", "confidence": 0.77}
    _, _, _, extra = resolve_affect(inf, kind="binary_confusion")
    assert extra["p_confused"] == pytest.approx(0.77)
    inf0 = {"engagement_level": 0, "label": "not_confused", "confidence": 0.90}
    _, _, _, extra0 = resolve_affect(inf0, kind="binary_confusion")
    assert extra0["p_confused"] == pytest.approx(0.10)


def test_facial_channel_finally_votes_on_confused():
    """The whole point: under the engagement stand-in this slot is 0.0."""
    canon = facial_to_canonical(_inference(0.75), kind="binary_confusion")
    i_conf = CANONICAL_ORDER.index("confused")
    assert canon[i_conf] == pytest.approx(0.75)
    assert canon[i_conf] > 0.0

    stand_in = facial_to_canonical(
        {"probs": [0.1, 0.2, 0.4, 0.3], "confidence": 0.4, "engagement_level": 2},
        kind="engagement")
    assert stand_in[i_conf] == 0.0, "engagement stand-in cannot see confusion — regression guard"


def test_unseeable_states_stay_zero():
    canon = facial_to_canonical(_inference(0.9), kind="binary_confusion")
    assert canon[CANONICAL_ORDER.index("bored")] == 0.0
    assert canon[CANONICAL_ORDER.index("frustrated")] == 0.0
    assert canon.sum() == pytest.approx(1.0)


def test_malformed_probs_degrade_to_zeros_not_a_crash():
    assert facial_to_canonical({"probs": [0.5]}, kind="binary_confusion").sum() == 0.0
    assert facial_to_canonical({}, kind="binary_confusion").sum() == 0.0


def test_fusion_combines_both_confusion_votes():
    """Both channels agreeing on confusion must produce a confused fused state."""
    facial = _inference(0.80)
    behavioural = {"label": "confused", "confidence": 0.85,
                   # BEHAVIORAL_CLASS_ORDER = (engaged, bored, confused, frustrated)
                   "probs": [0.15, 0.0, 0.85, 0.0]}
    fused = fuse_modalities(facial_result=facial, behavioral_result=behavioural,
                            facial_kind="binary_confusion")
    assert fused["affect_state"] == "confused"
    assert fused["facial_confidence"] == pytest.approx(0.80)
    assert fused["behavioral_confidence"] == pytest.approx(0.85)
    assert fused["fused_probs"][CANONICAL_ORDER.index("confused")] > 0.5


def test_fusion_still_degrades_to_one_modality():
    facial = _inference(0.9)
    only_facial = fuse_modalities(facial_result=facial, behavioral_result=None,
                                  facial_kind="binary_confusion")
    assert only_facial["affect_state"] == "confused"
    assert only_facial["behavioral_confidence"] == 0.0
