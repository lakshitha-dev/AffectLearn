"""Tests for the `behavioral_window` WebSocket handler (Story 4.4b AC5/AC7).

Drives the real graph with `predict_from_window` faked at the node module, and
monkeypatches the research emitter — no model file or live socket needed.
"""

import pytest

import app.agents.nodes.affect_detection as ad
import app.api.routes.ws as ws


@pytest.fixture
def captured_events(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(ws, "emit_research_event", fake_emit)
    return events


def _envelope(cycle=1, idle=False, events=None):
    return {
        "type": "behavioral_window",
        "ts": 1,
        "data": {
            "cycle_number": cycle,
            "capture_started_at_wall": 0,
            "events": events if events is not None else [{"kind": "mouse_click", "t_wall": 500}],
            "summary": {
                "mouse_sample_count": 3,
                "mouse_click_count": 1,
                "keystroke_count": 0,
                "scroll_event_count": 0,
                "idle": idle,
            },
        },
    }


@pytest.mark.asyncio
async def test_success_emits_behavioral_affect_event(monkeypatch, captured_events):
    def fake_predict(events, started):
        return {"affect_index": 1, "label": "bored", "confidence": 0.66,
                "probs": [0.2, 0.66, 0.1, 0.04], "n_bins": 30,
                "features": [[0.1, 0.2], [0.3, 0.4]]}

    monkeypatch.setattr(ad, "predict_from_window", fake_predict)
    await ws._handle_behavioral_window(_envelope(), "u1", "s1")

    assert len(captured_events) == 1
    ev = captured_events[0]
    assert ev["event_type"] == "behavioral_affect_detected"
    assert ev["learner_id"] == "u1" and ev["session_id"] == "s1" and ev["cycle_number"] == 1
    p = ev["payload"]
    assert p["affect_state"] == "bored"
    assert p["detection_mode"] == "behavioral_only"
    assert p["affect_source"] == "behavioral_model"
    assert p["affect_confidence"] == 0.66
    assert p["probs"] == [0.2, 0.66, 0.1, 0.04]
    assert p["n_bins"] == 30
    assert p["event_counts"]["mouse_click_count"] == 1
    # aggregate feature window persisted for training (train/serve parity, guide §7)
    assert p["features"] == [[0.1, 0.2], [0.3, 0.4]]


@pytest.mark.asyncio
async def test_idle_window_flagged_but_still_classifies(monkeypatch, captured_events):
    def fake_predict(events, started):
        return {"affect_index": 0, "label": "engaged", "confidence": 0.5,
                "probs": [0.5, 0.2, 0.2, 0.1], "n_bins": 30}

    monkeypatch.setattr(ad, "predict_from_window", fake_predict)
    await ws._handle_behavioral_window(_envelope(idle=True, events=[]), "u1", "s1")

    p = captured_events[0]["payload"]
    assert p["idle"] is True
    assert p["affect_state"] == "engaged"   # idle still classifies the zero-window


@pytest.mark.asyncio
async def test_model_unavailable_is_swallowed(monkeypatch, captured_events):
    def boom(events, started):
        raise FileNotFoundError("no behavioral model on disk")

    monkeypatch.setattr(ad, "predict_from_window", boom)
    await ws._handle_behavioral_window(_envelope(), "u1", "s1")  # must not raise

    assert captured_events[0]["payload"]["error"] == "behavioral_model_unavailable"


@pytest.mark.asyncio
async def test_inference_error_is_swallowed(monkeypatch, captured_events):
    def boom(events, started):
        raise RuntimeError("boom")

    monkeypatch.setattr(ad, "predict_from_window", boom)
    await ws._handle_behavioral_window(_envelope(), "u1", "s1")  # must not raise

    assert captured_events[0]["payload"]["error"] == "inference_error"
