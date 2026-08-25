"""Facial label vocabulary must follow the loaded artifact, not a fixed 4-tuple.

`CLASS_LABELS` was hardcoded to the DAiSEE engagement levels and indexed with a 2-class argmax,
so every facial label written to `research_events` came out as "very_low"/"low". Prediction was
unaffected (downstream reads the index and `probs`), but the durable record was wrong -- and the
record is the deliverable.
"""

from __future__ import annotations

import pytest

from app.services.model_inference import class_labels


@pytest.fixture(autouse=True)
def _clear_kind(monkeypatch):
    monkeypatch.delenv("AFFECT_MODEL_KIND", raising=False)


def test_binary_confusion_gets_the_binary_vocabulary():
    assert class_labels("binary_confusion") == ("not_confused", "confused")


def test_index_one_is_confused_matching_the_adapter():
    """Must agree with affect_mapping.BINARY_CONFUSED_INDEX, or labels invert silently."""
    from app.agents.affect_mapping import BINARY_CONFUSED_INDEX

    assert class_labels("binary_confusion")[BINARY_CONFUSED_INDEX] == "confused"


def test_engagement_keeps_the_four_daisee_levels():
    assert class_labels("engagement") == ("very_low", "low", "high", "very_high")


def test_category_uses_canonical_affect_order():
    from app.agents.affect_mapping import AFFECT_CLASS_ORDER

    assert class_labels("category") == tuple(AFFECT_CLASS_ORDER)


def test_resolves_from_env_when_kind_omitted(monkeypatch):
    monkeypatch.setenv("AFFECT_MODEL_KIND", "binary_confusion")
    assert class_labels() == ("not_confused", "confused")


def test_unknown_kind_falls_back_rather_than_raising():
    assert class_labels("something_new") == ("very_low", "low", "high", "very_high")


def test_binary_vocabulary_is_shorter_than_the_old_hardcoded_one():
    """The actual defect: a 2-class argmax indexed into a 4-name list produced valid-looking junk."""
    assert len(class_labels("binary_confusion")) == 2
    assert "very_low" not in class_labels("binary_confusion")
