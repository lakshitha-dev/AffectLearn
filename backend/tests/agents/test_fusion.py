"""Unit tests for multimodal late fusion (Story 4.4c AC1/AC2/AC4)."""

import numpy as np

from app.agents.fusion import (
    CANONICAL_ORDER,
    behavioral_to_canonical,
    facial_to_canonical,
    forced_mode,
    fuse_modalities,
)


def test_canonical_order_is_affect_states():
    assert CANONICAL_ORDER == ("bored", "confused", "engaged", "frustrated")


def test_behavioral_to_canonical_reorders():
    # behavioral order: engaged, bored, confused, frustrated
    c = behavioral_to_canonical([0.4, 0.3, 0.2, 0.1])
    # canonical: bored, confused, engaged, frustrated
    assert np.allclose(c, [0.3, 0.2, 0.4, 0.1])


def test_facial_to_canonical_engagement_mass():
    c = facial_to_canonical({"probs": [0.1, 0.2, 0.5, 0.2]}, kind="engagement")
    # bored = very_low+low = 0.3 ; engaged = high+very_high = 0.7 ; confused=frustrated=0
    assert np.allclose(c, [0.3, 0.0, 0.7, 0.0])


def test_facial_to_canonical_category_passthrough():
    c = facial_to_canonical({"probs": [0.1, 0.2, 0.6, 0.1]}, kind="category")
    assert np.allclose(c, [0.1, 0.2, 0.6, 0.1])


def test_fuse_higher_confidence_dominates():
    facial = {"confidence": 0.9, "probs": [0.0, 0.0, 1.0, 0.0]}      # engagement -> engaged
    behavioral = {"confidence": 0.2, "probs": [0.0, 0.0, 1.0, 0.0]}  # behavioral order -> confused
    out = fuse_modalities(facial_result=facial, behavioral_result=behavioral, facial_kind="engagement")
    assert out["affect_state"] == "engaged"                  # high-confidence facial wins
    assert out["weights"]["facial"] > out["weights"]["behavioral"]
    assert out["facial_confidence"] == 0.9 and out["behavioral_confidence"] == 0.2
    assert out["affect_source"] == "fusion"
    assert abs(sum(out["fused_probs"]) - 1.0) < 1e-6


def test_fuse_single_modality_degrades():
    behavioral = {"confidence": 0.6, "probs": [0.0, 0.0, 1.0, 0.0]}  # -> confused
    out = fuse_modalities(behavioral_result=behavioral)
    assert out["affect_state"] == "confused"
    assert out["behavioral_confidence"] == 0.6
    assert out["facial_confidence"] == 0.0


def test_forced_mode_default_and_validation(monkeypatch):
    monkeypatch.delenv("AFFECT_DETECTION_MODE", raising=False)
    assert forced_mode() == "auto"
    monkeypatch.setenv("AFFECT_DETECTION_MODE", "behavioral_only")
    assert forced_mode() == "behavioral_only"
    monkeypatch.setenv("AFFECT_DETECTION_MODE", "garbage")
    assert forced_mode() == "auto"
