"""Unit tests for the behavioral branch of affect_detection_node (Story 4.4b AC4)."""

import pytest

import app.agents.nodes.affect_detection as ad
from app.agents.state import AFFECT_SOURCE_BEHAVIORAL, make_initial_state

pytestmark = pytest.mark.asyncio


def _behavioral_state():
    return make_initial_state(
        learner_id="u1", session_id="s1", cycle_number=1,
        behavioral_payload={
            "events": [{"kind": "mouse_click", "t_wall": 1}],
            "capture_started_at_wall": 0,
        },
    )


async def test_behavioral_branch_writes_state(monkeypatch):
    def fake_predict(events, started):
        return {"affect_index": 2, "label": "confused", "confidence": 0.71,
                "probs": [0.1, 0.1, 0.71, 0.09], "n_bins": 30}

    monkeypatch.setattr(ad, "predict_from_window", fake_predict)
    update = await ad.affect_detection_node(_behavioral_state())

    assert update["affect_state"] == "confused"
    assert update["detection_mode"] == "behavioral_only"
    assert update["affect_source"] == AFFECT_SOURCE_BEHAVIORAL
    assert update["affect_confidence"] == pytest.approx(0.71)
    assert update["behavioral_inference"]["n_bins"] == 30


async def test_behavioral_branch_does_not_swallow_error(monkeypatch):
    def boom(events, started):
        raise RuntimeError("inference blew up")

    monkeypatch.setattr(ad, "predict_from_window", boom)
    with pytest.raises(RuntimeError):
        await ad.affect_detection_node(_behavioral_state())


async def test_detection_mode_behavioral_only_when_only_behavioral_present():
    state = _behavioral_state()
    assert ad._resolve_detection_mode(state) == "behavioral_only"


async def test_detection_mode_facial_only_for_facial_cycle():
    state = make_initial_state(
        learner_id="u1", session_id="s1", cycle_number=1,
        facial_payload={"frames_b64": "x", "frames_captured": 30},
    )
    assert ad._resolve_detection_mode(state) == "facial_only"
