"""Unit tests for affect-category resolution (Story 4.4 AC6)."""

import pytest

from app.agents.affect_mapping import (
    AFFECT_CLASS_ORDER,
    category_confidence,
    engagement_to_affect,
    index_to_affect,
    resolve_affect,
)
from app.agents.state import AFFECT_SOURCE_CATEGORY, AFFECT_SOURCE_ENGAGEMENT


# ── category model path ──────────────────────────────────────────────────────
def test_index_to_affect_maps_all_four_classes():
    assert [index_to_affect(i) for i in range(4)] == list(AFFECT_CLASS_ORDER)
    assert AFFECT_CLASS_ORDER == ("bored", "confused", "engaged", "frustrated")


def test_index_to_affect_out_of_range_defaults_bored():
    assert index_to_affect(9) == "bored"
    assert index_to_affect(-1) == "bored"


# ── engagement stand-in path ─────────────────────────────────────────────────
def test_engagement_to_affect_collapse():
    assert engagement_to_affect(0) == "bored"      # very_low
    assert engagement_to_affect(1) == "bored"      # low
    assert engagement_to_affect(2) == "engaged"    # high
    assert engagement_to_affect(3) == "engaged"    # very_high


def test_engagement_to_affect_out_of_range_defaults_bored():
    assert engagement_to_affect(-5) == "bored"


# ── category confidence aggregation (M1) ─────────────────────────────────────
def test_category_confidence_engagement_adapter_aggregates_collapsed_levels():
    # high(2)+very_high(3) collapse to "engaged" -> confidence is their summed mass,
    # not the single argmax prob (0.55 here, not 0.45).
    inf = {"engagement_level": 2, "confidence": 0.45, "probs": [0.05, 0.4, 0.45, 0.1]}
    assert category_confidence(inf, "engaged", "engagement") == pytest.approx(0.55)
    # low(1)+very_low(0) collapse to "bored" -> 0.05 + 0.4 = 0.45
    assert category_confidence(inf, "bored", "engagement") == pytest.approx(0.45)


def test_category_confidence_category_model_uses_raw_prob():
    inf = {"engagement_level": 1, "confidence": 0.7, "probs": [0.1, 0.7, 0.1, 0.1]}
    assert category_confidence(inf, "confused", "category") == pytest.approx(0.7)


def test_category_confidence_falls_back_without_probs():
    inf = {"engagement_level": 2, "confidence": 0.83}  # no probs
    assert category_confidence(inf, "engaged", "engagement") == pytest.approx(0.83)


# ── resolve_affect dispatch + provenance ─────────────────────────────────────
def test_resolve_affect_engagement_kind_stamps_source_and_preserves_raw():
    inf = {"engagement_level": 2, "label": "high", "confidence": 0.9,
           "probs": [0.05, 0.05, 0.7, 0.2]}
    affect, source, confidence, extra = resolve_affect(inf, kind="engagement")
    assert affect == "engaged"
    assert source == AFFECT_SOURCE_ENGAGEMENT
    assert confidence == pytest.approx(0.9)  # probs[2]+probs[3] = 0.7+0.2
    assert extra == {"engagement_level": 2, "engagement_label": "high"}


def test_resolve_affect_category_kind_maps_index_directly():
    inf = {"engagement_level": 1, "label": "ignored", "confidence": 0.7,
           "probs": [0.1, 0.7, 0.1, 0.1]}
    affect, source, confidence, extra = resolve_affect(inf, kind="category")
    assert affect == "confused"            # index 1 -> AFFECT_CLASS_ORDER[1]
    assert source == AFFECT_SOURCE_CATEGORY
    assert confidence == pytest.approx(0.7)  # single-class prob, no aggregation
    assert extra == {}                     # no engagement fields under category model


def test_resolve_affect_defaults_to_engagement_kind(monkeypatch):
    monkeypatch.delenv("AFFECT_MODEL_KIND", raising=False)
    affect, source, _, _ = resolve_affect({"engagement_level": 3, "label": "very_high", "confidence": 1.0})
    assert affect == "engaged"
    assert source == AFFECT_SOURCE_ENGAGEMENT
