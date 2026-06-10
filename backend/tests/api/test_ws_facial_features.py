"""Tests for the `facial_features` WebSocket handler wiring (Story 4.4).

The handler now drives the LangGraph cycle (`get_graph().ainvoke`). Inference is
faked by patching `detect_engagement` on the affect_detection node module (the graph
node calls that module global), and the research-event emitter is monkeypatched, so
no model file or live socket is needed.
"""

import pytest

import app.api.routes.ws as ws
import app.agents.nodes.affect_detection as ad


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

    monkeypatch.setattr(ad, "detect_engagement", fake_detect)
    await ws._handle_facial_features(_envelope(), "u1", "s1")

    assert len(captured_events) == 1
    ev = captured_events[0]
    assert ev["event_type"] == "facial_affect_detected"
    assert ev["learner_id"] == "u1" and ev["session_id"] == "s1" and ev["cycle_number"] == 1
    p = ev["payload"]
    # raw engagement output preserved (superset constraint from earlier stories)
    assert p["engagement_level"] == 2 and p["label"] == "high"
    assert p["confidence"] == 0.8312 and p["frames_used"] == 16
    assert p["frames_captured"] == 30 and p["dropped_frames"] == 2
    # H1: full softmax distribution preserved for research (recoverable for remapping)
    assert p["probs"] == [0.1, 0.1, 0.7, 0.1]
    # Story 4.4 additions: 4-category affect + provenance
    assert p["affect_state"] == "engaged"
    assert p["detection_mode"] == "facial_only"
    assert p["affect_source"] == "engagement_adapter"
    # M1: confidence is the collapsed category mass (probs[2]+probs[3]=0.8), not 0.8312
    assert p["affect_confidence"] == 0.8


@pytest.mark.asyncio
async def test_empty_cycle_flagged(monkeypatch, captured_events):
    async def fake_detect(_data):
        return None

    monkeypatch.setattr(ad, "detect_engagement", fake_detect)
    await ws._handle_facial_features(_envelope(frames_captured=0, frames_b64=""), "u1", "s1")

    assert captured_events[0]["payload"]["empty_cycle"] is True
    assert "affect_state" not in captured_events[0]["payload"]


@pytest.mark.asyncio
async def test_model_unavailable_is_swallowed(monkeypatch, captured_events):
    async def fake_detect(_data):
        raise FileNotFoundError("no model on disk")

    monkeypatch.setattr(ad, "detect_engagement", fake_detect)
    await ws._handle_facial_features(_envelope(), "u1", "s1")  # must not raise

    assert captured_events[0]["payload"]["error"] == "model_unavailable"


@pytest.mark.asyncio
async def test_inference_error_is_swallowed(monkeypatch, captured_events):
    async def fake_detect(_data):
        raise RuntimeError("boom")

    monkeypatch.setattr(ad, "detect_engagement", fake_detect)
    await ws._handle_facial_features(_envelope(), "u1", "s1")  # must not raise

    assert captured_events[0]["payload"]["error"] == "inference_error"
