"""One inbound sensing message = one graph run = one `decision_id` (migration 031).

The detection, the gate verdict, the strategy, the content and the delivery are emitted from
different modules. These tests pin that everything emitted inside a `decision_scope` shares one id
-- including from child tasks, which is how LangGraph runs parallel branches -- that nothing
outside a scope is given one, and that the id reaches the ledger row and the stored event.
"""

import asyncio

import pytest
from sqlalchemy import select

from app.models.assistance_event import AssistanceEvent
from app.models.research_event import ResearchEvent
from app.services import assistance_service, model_report, research_event_service, research_logger


@pytest.fixture
def published(monkeypatch):
    out: list[dict] = []

    async def fake_stream_add(stream, value):
        out.append(value)
        return "1-0"

    async def no_incr(key, ttl_seconds=None):
        return None

    monkeypatch.setattr(research_logger.redis_service, "stream_add", fake_stream_add)
    monkeypatch.setattr(research_logger.redis_service, "incr", no_incr)
    return out


@pytest.mark.asyncio
async def test_every_event_in_a_scope_shares_one_decision_id(published):
    with research_logger.decision_scope() as decision_id:
        await research_logger.emit({"event_type": "facial_affect_detected", "session_id": "s1"})

        async def branch(name):
            await research_logger.emit({"event_type": name, "session_id": "s1"})

        # LangGraph runs parallel nodes as tasks; a task copies the context it was created in.
        await asyncio.gather(branch("adaptation_triggered"), branch("video_resource_found"))

    assert {e["decision_id"] for e in published} == {decision_id}
    assert len(decision_id) == 36


@pytest.mark.asyncio
async def test_events_outside_a_scope_carry_no_decision_id(published):
    with research_logger.decision_scope():
        pass
    await research_logger.emit({"event_type": "self_report", "session_id": "s1"})
    assert published[-1]["decision_id"] is None


@pytest.mark.asyncio
async def test_two_runs_get_different_ids(published):
    with research_logger.decision_scope() as first:
        await research_logger.emit({"event_type": "a", "session_id": "s1"})
    with research_logger.decision_scope() as second:
        await research_logger.emit({"event_type": "a", "session_id": "s1"})
    assert first != second
    assert [e["decision_id"] for e in published] == [first, second]


@pytest.mark.asyncio
async def test_an_explicit_decision_id_on_the_event_wins(published):
    with research_logger.decision_scope():
        await research_logger.emit({"event_type": "a", "session_id": "s1", "decision_id": "replayed"})
    assert published[-1]["decision_id"] == "replayed"


@pytest.mark.asyncio
async def test_decision_id_is_persisted_as_a_column(db):
    await research_event_service.persist_batch(db, [{
        "event_type": "strategy_decided", "session_id": "s1", "cycle_number": 1,
        "timestamp": 1, "sequence_number": 1, "payload": {},
        "event_id": "e-1", "decision_id": "d-1",
    }])
    row = (await db.execute(select(ResearchEvent))).scalar_one()
    assert row.decision_id == "d-1"


@pytest.mark.asyncio
async def test_the_ledger_row_carries_the_decision_id(db, test_user):
    await assistance_service.record_delivery(
        db, adaptation_id="ad-1", learner_id=test_user.id, session_id="s1", cycle_number=3,
        action_type="show_hint", delivered=True, decision_id="d-9",
    )
    row = (await db.execute(select(AssistanceEvent))).scalar_one()
    assert row.decision_id == "d-9"


# ── what the facial event now records ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_facial_event_records_timing_and_geometry_features(monkeypatch):
    import app.agents.nodes.affect_detection as ad
    import app.api.routes.ws as ws

    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    features = {f"mean_{c}": 0.1 for c in ("gaze_x", "gaze_y", "mouth_open", "motion")}

    async def fake_detect(_data):
        return {"engagement_level": 1, "class_index": 1, "label": "disengaged",
                "confidence": 0.83, "probs": [0.17, 0.83], "model_kind": "geometry",
                "features": features}

    monkeypatch.setattr(ws, "emit_research_event", fake_emit)
    monkeypatch.setattr(ad, "detect_engagement", fake_detect)
    envelope = {"type": "facial_features", "data": {
        "cycle_number": 4, "frames_captured": 30, "dropped_frames": 0,
        "capture_started_at": 1_790_000_000_000, "capture_ended_at": 1_790_000_030_000,
        "geometry": [[0.0] * 11] * 10,
    }}
    await ws._handle_facial_features(envelope, "u1", "s1")

    payload = next(e for e in events if e["event_type"] == "facial_affect_detected")["payload"]
    assert payload["client_window"] == [1_790_000_000_000, 1_790_000_030_000]
    assert isinstance(payload["received_at_ms"], int) and payload["graph_ms"] >= 0
    assert payload["geometry_features"] == features


def test_geometry_inference_returns_the_named_model_input():
    from app.services import geometry_inference as gi

    frames = [[0.1, 0.0, 0.0, 0.3, 0.3, 0.3, 0.02, 0.05 * i, -0.02, 0.01, 1.0] for i in range(10)]
    out = gi.predict_from_payload({"geometry": frames})
    assert out is not None
    assert list(out["features"]) == list(gi.FEATURE_NAMES)
    assert len(out["features"]) == 20


# ── session provenance ──────────────────────────────────────────────────────────


def test_provenance_names_models_config_and_llm_without_secrets(monkeypatch):
    monkeypatch.setenv("APP_COMMIT", "abc1234")
    prov = model_report.provenance()
    assert prov["app_commit"] == "abc1234"
    assert set(prov["models"]) == {"facial", "behavioral"}
    assert prov["models"]["behavioral"]["path"]
    assert "withhold_rate" in prov["gate"] and "version" in prov["gate"]
    assert set(prov["llm"]) == {"endpoint_host", "model", "timeout_s", "max_tokens"}
    assert "key" not in str(prov).lower()


def test_provenance_hashes_an_existing_artifact(tmp_path, monkeypatch):
    artifact = tmp_path / "m.onnx"
    artifact.write_bytes(b"model-bytes")
    monkeypatch.setenv("BEHAVIORAL_MODEL_PATH", str(artifact))
    import hashlib

    prov = model_report.provenance()
    assert prov["models"]["behavioral"]["sha256"] == hashlib.sha256(b"model-bytes").hexdigest()
