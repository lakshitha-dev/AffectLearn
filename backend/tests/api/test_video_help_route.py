"""POST /learners/me/video-help and /learners/me/video-help/closed."""

import uuid

import pytest

import app.api.routes.learners as learners
from app.services import content_context_service, video_resource_agent

pytestmark = pytest.mark.asyncio

SECTION = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def stubbed(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    async def fake_build(section_id, _db):
        return {"topic": "Loops", "lesson": "range", "section_id": section_id}

    async def fake_find(context, hint_text=None):
        return {"kind": "embed", "video_id": "BBB", "title": "Why range stops early",
                "channel": "Y", "duration_s": 300, "url": "https://www.youtube.com/watch?v=BBB",
                "query": "q", "concept": "range", "reason": "Shows it.", "source": "api"}

    monkeypatch.setattr(learners, "emit_research_event", fake_emit)
    monkeypatch.setattr(content_context_service, "build", fake_build)
    monkeypatch.setattr(video_resource_agent, "find_video", fake_find)
    learners._last_video_help.clear()
    return events


async def test_a_learner_gets_a_video_and_the_request_is_recorded(client, auth_headers, stubbed):
    resp = await client.post(
        "/api/v1/learners/me/video-help",
        json={"sectionId": SECTION, "adaptationId": "a1", "hintText": "Think about 0."},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "embed"
    assert body["videoId"] == "BBB"
    assert body["reason"] == "Shows it."
    # Only what the learner sees: no query internals or affect on the wire.
    assert "query" not in body and "source" not in body

    types = [e["event_type"] for e in stubbed]
    assert types == ["video_help_requested", "video_help_served"]
    assert stubbed[1]["payload"]["from_adaptation_id"] == "a1"
    assert stubbed[1]["payload"]["source"] == "api"


async def test_designers_cannot_use_it(client, designer_headers):
    resp = await client.post(
        "/api/v1/learners/me/video-help", json={"sectionId": SECTION}, headers=designer_headers
    )
    assert resp.status_code == 403


async def test_a_rapid_second_request_is_throttled_to_a_link(client, auth_headers, stubbed):
    await client.post("/api/v1/learners/me/video-help", json={"sectionId": SECTION},
                      headers=auth_headers)
    resp = await client.post("/api/v1/learners/me/video-help", json={"sectionId": SECTION},
                             headers=auth_headers)
    assert resp.json()["kind"] == "link"
    assert resp.json()["throttled"] is True
    assert [e["event_type"] for e in stubbed].count("video_help_served") == 1


async def test_closing_records_how_long_it_was_open(client, auth_headers, stubbed):
    resp = await client.post(
        "/api/v1/learners/me/video-help/closed",
        json={"sectionId": SECTION, "videoId": "BBB", "secondsOpen": 95.44},
        headers=auth_headers,
    )
    assert resp.status_code == 204
    assert stubbed[-1]["event_type"] == "video_help_closed"
    assert stubbed[-1]["payload"] == {"video_id": "BBB", "seconds_open": 95.4}
