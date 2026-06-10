"""Tests for WS multimodal pairing + ablation forcing (Story 4.4c AC4/AC5)."""

import pytest

import app.agents.nodes.affect_detection as ad
import app.api.routes.ws as ws
from app.services import fusion_buffer


@pytest.fixture(autouse=True)
def _reset_buffer():
    fusion_buffer._reset()
    yield
    fusion_buffer._reset()


@pytest.fixture
def captured(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(ws, "emit_research_event", fake_emit)
    return events


def _facial_env(cycle=1):
    return {"type": "facial_features", "ts": 1, "data": {
        "cycle_number": cycle, "frames_captured": 30, "dropped_frames": 0, "frames_b64": "AAAA"}}


def _behavioral_env(cycle=1):
    return {"type": "behavioral_window", "ts": 1, "data": {
        "cycle_number": cycle, "capture_started_at_wall": 0,
        "events": [{"kind": "mouse_click", "t_wall": 1}], "summary": {"idle": False}}}


def _patch_inference(monkeypatch):
    async def fake_facial(_data):
        return {"engagement_level": 2, "label": "high", "confidence": 0.8,
                "probs": [0.05, 0.05, 0.8, 0.1], "frames_used": 16}

    def fake_behavioral(events, started):
        return {"affect_index": 2, "label": "confused", "confidence": 0.4,
                "probs": [0.1, 0.2, 0.6, 0.1], "n_bins": 30}

    monkeypatch.setattr(ad, "detect_engagement", fake_facial)
    monkeypatch.setattr(ad, "predict_from_window", fake_behavioral)


@pytest.mark.asyncio
async def test_pair_emits_multimodal_event(monkeypatch, captured):
    _patch_inference(monkeypatch)
    monkeypatch.setenv("AFFECT_DETECTION_MODE", "auto")

    await ws._handle_facial_features(_facial_env(), "u1", "s1")
    await ws._handle_behavioral_window(_behavioral_env(), "u1", "s1")

    types = [e["event_type"] for e in captured]
    assert "facial_affect_detected" in types
    assert "behavioral_affect_detected" in types
    assert "multimodal_affect_detected" in types

    mm = next(e for e in captured if e["event_type"] == "multimodal_affect_detected")["payload"]
    assert mm["detection_mode"] == "multimodal"
    assert mm["affect_source"] == "fusion"
    # facial(engaged, conf .8) dominates behavioral(confused, conf .4) -> fused engaged
    assert mm["affect_state"] == "engaged"
    assert "facial_confidence" in mm and "behavioral_confidence" in mm
    assert mm["weights"]["facial"] > mm["weights"]["behavioral"]   # facial 0.8 > behavioral 0.4
    assert mm["forced_mode"] == "auto"

    # every unimodal event carries the ablation marker
    for e in captured:
        if e["event_type"] in ("facial_affect_detected", "behavioral_affect_detected"):
            assert e["payload"]["forced_mode"] == "auto"


@pytest.mark.asyncio
async def test_facial_only_mode_suppresses_fusion(monkeypatch, captured):
    _patch_inference(monkeypatch)
    monkeypatch.setenv("AFFECT_DETECTION_MODE", "facial_only")

    await ws._handle_facial_features(_facial_env(), "u1", "s1")
    await ws._handle_behavioral_window(_behavioral_env(), "u1", "s1")

    types = [e["event_type"] for e in captured]
    assert "multimodal_affect_detected" not in types
    for e in captured:
        if "forced_mode" in e["payload"]:
            assert e["payload"]["forced_mode"] == "facial_only"
