"""Tests for the `facial_features` WebSocket handler wiring (Story 4.4).

Exercises `_handle_facial_features` directly with `detect_engagement` and the
research-event emitter monkeypatched, so no model file or live socket is needed.
"""

import pytest

import app.api.routes.ws as ws


@pytest.fixture
def captured_events(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    # _safe_emit() awaits the module-level emit_research_event alias.
    monkeypatch.setattr(ws, "emit_research_event", fake_emit)
    return events


def _envelope(frames_captured=30, dropped=2, cycle=1, frames_b64="AAAA"):
    return {
        "type": "facial_features",
        "ts": 1,
        "data": {
            "cycle_number": cycle,
            "frames_captured": frames_captured,
            "dropped_frames": dropped,
            "frames_b64": frames_b64,
        },
    }


@pytest.mark.asyncio
async def test_success_emits_affect_event(monkeypatch, captured_events):
    async def fake_detect(_data):
        return {"engagement_level": 2, "label": "high", "confidence": 0.8312,
                "probs": [0.1, 0.1, 0.7, 0.1], "frames_used": 16}

    monkeypatch.setattr(ws, "detect_engagement", fake_detect)
    await ws._handle_facial_features(_envelope(), "u1", "s1")

    assert len(captured_events) == 1
    ev = captured_events[0]
    assert ev["event_type"] == "facial_affect_detected"
    assert ev["learner_id"] == "u1" and ev["session_id"] == "s1" and ev["cycle_number"] == 1
    p = ev["payload"]
    assert p["engagement_level"] == 2 and p["label"] == "high"
    assert p["confidence"] == 0.8312 and p["frames_used"] == 16
    assert p["frames_captured"] == 30 and p["dropped_frames"] == 2


@pytest.mark.asyncio
async def test_empty_cycle_flagged(monkeypatch, captured_events):
    async def fake_detect(_data):
        return None

    monkeypatch.setattr(ws, "detect_engagement", fake_detect)
    await ws._handle_facial_features(_envelope(frames_captured=0, frames_b64=""), "u1", "s1")

    assert captured_events[0]["payload"]["empty_cycle"] is True


@pytest.mark.asyncio
async def test_model_unavailable_is_swallowed(monkeypatch, captured_events):
    async def fake_detect(_data):
        raise FileNotFoundError("no model on disk")

    monkeypatch.setattr(ws, "detect_engagement", fake_detect)
    await ws._handle_facial_features(_envelope(), "u1", "s1")  # must not raise

    assert captured_events[0]["payload"]["error"] == "model_unavailable"


@pytest.mark.asyncio
async def test_inference_error_is_swallowed(monkeypatch, captured_events):
    async def fake_detect(_data):
        raise RuntimeError("boom")

    monkeypatch.setattr(ws, "detect_engagement", fake_detect)
    await ws._handle_facial_features(_envelope(), "u1", "s1")  # must not raise

    assert captured_events[0]["payload"]["error"] == "inference_error"
