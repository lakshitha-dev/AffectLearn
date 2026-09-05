"""The research-event envelope carries WHERE IN THE COURSE a cycle happened (migration 021).

Before this, affect and adaptation events were keyed by `session_id` + `cycle_number` alone.
`analytics_service` records the consequence in its own header — its per-section aggregations are
best-effort and the affect heatmap falls back to `section_progress.affect_states`, a list the
CLIENT posts on completion, rather than the model's own output.

These tests pin the contract at the WebSocket boundary: a cycle on a known section is stamped,
a cycle with no section is not stamped at all, and the coordinates never leak into `payload`
(where `research_event_service._row` could not column them).

Inference is faked, as in the sibling `test_ws_facial_features` / `test_ws_behavioral_window`
suites, so no model file or live socket is needed.
"""

import pytest

import app.agents.nodes.affect_detection as ad
import app.api.routes.ws as ws
from app.services import content_context_service

COURSE_ID = "11111111-1111-1111-1111-111111111111"
SECTION_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def captured_events(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(ws, "emit_research_event", fake_emit)
    return events


@pytest.fixture
def on_a_known_section(monkeypatch):
    """Stand in for the cached section lookup, so these tests exercise the STAMPING rather than
    re-testing the resolver (covered in tests/services/test_content_context_coordinates.py)."""
    async def fake_build(section_id, _db):
        if not section_id:
            return {}
        return {
            "topic": "Generics", "lesson": "Type Systems", "body": "...",
            "difficulty": "unknown",
            "section_id": SECTION_ID, "lesson_id": "l1", "module_id": "m1",
            "course_id": COURSE_ID,
        }

    monkeypatch.setattr(content_context_service, "build", fake_build)


@pytest.fixture
def fake_facial_inference(monkeypatch):
    async def fake_detect(_data):
        return {"engagement_level": 2, "label": "high", "confidence": 0.83,
                "probs": [0.1, 0.1, 0.7, 0.1], "frames_used": 16}

    monkeypatch.setattr(ad, "detect_engagement", fake_detect)


def _facial(section_id=SECTION_ID, cycle=1):
    data = {"cycle_number": cycle, "frames_captured": 30, "dropped_frames": 0,
            "frames_b64": "AAAA"}
    if section_id is not None:
        data["section_id"] = section_id
    return {"type": "facial_features", "ts": 1, "data": data}


@pytest.mark.asyncio
async def test_facial_cycle_is_stamped_with_its_section(
    captured_events, on_a_known_section, fake_facial_inference
):
    await ws._handle_facial_features(_facial(), "u1", "s1")

    ev = captured_events[0]
    assert ev["event_type"] == "facial_affect_detected"
    assert ev["course_id"] == COURSE_ID
    assert ev["section_id"] == SECTION_ID


@pytest.mark.asyncio
async def test_coordinates_sit_on_the_envelope_not_in_the_payload(
    captured_events, on_a_known_section, fake_facial_inference
):
    """Same contract as phase/group: the worker columns TOP-LEVEL fields. A coordinate buried in
    `payload` is a JSON scan, not a join key, which is the problem this migration exists to fix."""
    await ws._handle_facial_features(_facial(), "u1", "s1")

    payload = captured_events[0]["payload"]
    assert "course_id" not in payload
    assert "section_id" not in payload


@pytest.mark.asyncio
async def test_cycle_with_no_section_carries_no_coordinates(
    captured_events, on_a_known_section, fake_facial_inference
):
    """A learner can be connected outside a lesson. That event is honestly uncoordinated rather
    than null-filled, so `section_id IS NOT NULL` keeps meaning "happened somewhere in a course"."""
    await ws._handle_facial_features(_facial(section_id=None), "u1", "s1")

    ev = captured_events[0]
    assert "course_id" not in ev
    assert "section_id" not in ev


@pytest.mark.asyncio
async def test_a_failed_cycle_is_still_located(
    captured_events, on_a_known_section, monkeypatch
):
    """The context is resolved OUTSIDE the try that wraps the graph, so an inference failure
    still yields a located event — knowing where a cycle failed is the point of recording it."""
    async def boom(_data):
        raise RuntimeError("inference exploded")

    monkeypatch.setattr(ad, "detect_engagement", boom)

    await ws._handle_facial_features(_facial(), "u1", "s1")

    ev = captured_events[0]
    assert ev["payload"]["error"] == "inference_error"
    assert ev["section_id"] == SECTION_ID


@pytest.mark.asyncio
async def test_self_report_label_is_stamped_with_its_section(captured_events):
    """`section_features` already joins self-reports on `payload.section_id`. Promoting it to the
    envelope makes that join an indexed one; the payload copy stays for existing readers."""
    envelope = {
        "type": "self_report", "ts": 1,
        "data": {"affect": "confused", "cycle_number": 3, "section_id": SECTION_ID},
    }

    await ws._handle_self_report(envelope, "u1", "s1")

    ev = captured_events[0]
    assert ev["event_type"] == "self_report"
    assert ev["section_id"] == SECTION_ID
    assert ev["payload"]["section_id"] == SECTION_ID


@pytest.mark.asyncio
async def test_self_report_without_a_section_is_not_stamped(captured_events):
    envelope = {"type": "self_report", "ts": 1, "data": {"skipped": True, "cycle_number": 3}}

    await ws._handle_self_report(envelope, "u1", "s1")

    assert "section_id" not in captured_events[0]
