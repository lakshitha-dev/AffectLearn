"""Unit tests for the affect_detection LangGraph node (Story 4.4 AC3/AC5/AC6)."""

import pytest

import app.agents.nodes.affect_detection as ad
from app.agents.state import AFFECT_SOURCE_ENGAGEMENT, make_initial_state

pytestmark = pytest.mark.asyncio


def _state(payload):
    return make_initial_state(
        learner_id="u1", session_id="s1", cycle_number=1, facial_payload=payload
    )


async def test_node_writes_affect_category_and_provenance(monkeypatch):
    async def fake_detect(_data):
        return {"engagement_level": 2, "label": "high", "confidence": 0.83,
                "probs": [0.1, 0.1, 0.7, 0.1], "frames_used": 16}

    monkeypatch.setattr(ad, "detect_engagement", fake_detect)
    update = await ad.affect_detection_node(_state({"frames_b64": "x", "frames_captured": 30}))

    assert update["affect_state"] == "engaged"           # one of the 4 categories
    assert update["affect_state"] in ("bored", "confused", "engaged", "frustrated")
    # confidence is the collapsed category's mass (probs[high]+probs[very_high]),
    # not the raw single-level argmax prob (0.83) — see M1 / category_confidence.
    assert update["affect_confidence"] == pytest.approx(0.8)
    assert update["detection_mode"] == "facial_only"
    assert update["affect_source"] == AFFECT_SOURCE_ENGAGEMENT
    assert update["engagement_level"] == 2 and update["engagement_label"] == "high"
    assert update["facial_inference"]["frames_used"] == 16


async def test_node_empty_cycle_sets_flag_without_affect(monkeypatch):
    async def fake_detect(_data):
        return None

    monkeypatch.setattr(ad, "detect_engagement", fake_detect)
    update = await ad.affect_detection_node(_state({"frames_b64": "", "frames_captured": 0}))

    assert update["empty_cycle"] is True
    assert update["detection_mode"] == "facial_only"
    assert "affect_state" not in update


async def test_node_does_not_swallow_inference_error(monkeypatch):
    async def boom(_data):
        raise RuntimeError("inference blew up")

    monkeypatch.setattr(ad, "detect_engagement", boom)
    with pytest.raises(RuntimeError):
        await ad.affect_detection_node(_state({"frames_b64": "x", "frames_captured": 30}))
