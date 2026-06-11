"""End-to-end affect pipeline integration (real models where available).

Drives the actual WS handlers through the compiled LangGraph with the REAL behavioral ONNX
model (no mocks), proving the wired path: model artifact -> feature extraction -> graph ->
affect_detection node -> research event. Facial degrades to `model_unavailable` because the
facial CNN-LSTM ONNX is not exported yet — drop `cnn_lstm_best.onnx` into `backend/models/`
(AFFECT_MODEL_KIND=engagement) to light up the facial path with zero code changes.
"""

import base64
import os

import numpy as np
import pytest

import app.agents.nodes.affect_detection as ad
import app.api.routes.ws as ws
import app.services.behavioral_inference as bi
import app.services.model_inference as mi

_BEHAVIORAL_MODEL = bi._DEFAULT_MODEL_PATH
_AFFECT_STATES = {"bored", "confused", "engaged", "frustrated"}


@pytest.fixture
def captured(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(ws, "emit_research_event", fake_emit)
    return events


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.path.exists(_BEHAVIORAL_MODEL),
    reason=f"behavioral ONNX not present at {_BEHAVIORAL_MODEL}",
)
async def test_behavioral_cycle_runs_through_real_model(captured, monkeypatch):
    # Use the REAL behavioral inference path (no node-level mock); reset the singleton
    # so it loads from the wired default path.
    monkeypatch.setattr(ad, "predict_from_window", bi.predict_from_window)
    bi._MODEL = None

    events = [
        {"kind": "scroll", "t_wall": 1000 + i * 1400, "delta_y": 40 if i % 2 else -40}
        for i in range(20)
    ]
    events += [
        {"kind": "key", "t_wall": 1000 + i * 1500, "category": "backspace" if i % 2 else "alpha"}
        for i in range(12)
    ]
    envelope = {
        "type": "behavioral_window", "ts": 1,
        "data": {
            "cycle_number": 1, "capture_started_at_wall": 1000, "events": events,
            "summary": {"idle": False, "mouse_sample_count": 0, "mouse_click_count": 0,
                        "keystroke_count": 12, "scroll_event_count": 20},
        },
    }
    await ws._handle_behavioral_window(envelope, "learner-e2e", "sess-e2e")

    assert len(captured) == 1
    payload = captured[0]["payload"]
    assert captured[0]["event_type"] == "behavioral_affect_detected"
    assert payload["affect_state"] in _AFFECT_STATES        # real Bi-LSTM produced a category
    assert payload["detection_mode"] == "behavioral_only"
    assert payload["affect_source"] == "behavioral_model"
    assert 0.0 <= payload["affect_confidence"] <= 1.0
    assert len(payload["probs"]) == 4


@pytest.mark.asyncio
async def test_facial_cycle_degrades_when_onnx_missing(captured):
    # Force the facial singleton unset; skip if a facial ONNX has since been dropped in.
    mi._MODEL = None
    if os.path.exists(mi._DEFAULT_MODEL_PATH):
        pytest.skip("facial ONNX present — degradation path not applicable")

    one_frame = np.zeros(mi.BYTES_PER_FRAME // 4, dtype=np.float32).tobytes()  # 1 valid frame
    frames_b64 = base64.b64encode(one_frame).decode()
    envelope = {
        "type": "facial_features", "ts": 1,
        "data": {"cycle_number": 1, "frames_captured": 1, "dropped_frames": 0,
                 "frames_b64": frames_b64},
    }
    await ws._handle_facial_features(envelope, "learner-e2e", "sess-e2e")

    # Graceful degradation: missing facial model -> logged, skipped cycle (socket survives).
    assert captured[0]["payload"]["error"] == "model_unavailable"
