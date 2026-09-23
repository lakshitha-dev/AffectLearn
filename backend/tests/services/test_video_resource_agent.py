"""The Video Resource Agent, with no network: model and YouTube calls are stubbed."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services import redis_service
from app.services import video_resource_agent as agent

pytestmark = pytest.mark.asyncio

CONTEXT = {
    "section_id": "sec-1",
    "topic": "Python loops",
    "lesson": "for and range",
    "body": "range(5) produces 0, 1, 2, 3, 4.",
    "learner_activity": {"quiz_incorrect_count": 2},
}

CANDIDATES = [
    {"video_id": "AAA", "title": "Loops overview", "channel": "X", "description": "",
     "duration_s": 400},
    {"video_id": "BBB", "title": "Why range stops early", "channel": "Y", "description": "",
     "duration_s": 300},
]


@pytest.fixture
def memory_cache(monkeypatch):
    store: dict = {}

    async def get_json(key):
        return store.get(key)

    async def set_json(key, value, ttl_seconds=None):
        store[key] = value

    monkeypatch.setattr(redis_service, "get_json", get_json)
    monkeypatch.setattr(redis_service, "set_json", set_json)
    return store


@pytest.fixture
def model(monkeypatch):
    """Scripted model replies, consumed in call order; None means the model is unavailable."""
    replies: list = []

    async def fake_ask(system, human, timeout_s=None):
        return replies.pop(0) if replies else None

    monkeypatch.setattr(agent, "_ask", fake_ask)
    return replies


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setattr(settings, "YOUTUBE_API_KEY", "test-key")


# ── pure helpers ─────────────────────────────────────────────────────────────────────


def test_parse_duration():
    assert agent.parse_duration("PT4M13S") == 253
    assert agent.parse_duration("PT1H2M") == 3720
    assert agent.parse_duration("PT45S") == 45
    assert agent.parse_duration("P1D") is None
    assert agent.parse_duration(None) is None


def test_fallback_query_uses_the_section_labels():
    query, concept = agent.fallback_query(CONTEXT)
    assert query == "Python loops for and range explained"
    assert concept == "Python loops for and range"
    assert agent.fallback_query({})[1] == "this concept"


def test_search_link_is_encoded():
    assert agent.search_link("for loop & range") == (
        "https://www.youtube.com/results?search_query=for+loop+%26+range"
    )


# ── the agent ────────────────────────────────────────────────────────────────────────


async def test_the_model_chooses_the_video(monkeypatch, memory_cache, model, api_key):
    model.extend([
        {"query": "python range stop value explained", "concept": "range end value"},
        {"video_id": "BBB", "reason": "It shows why range stops before 5."},
    ])

    async def fake_search(query, key):
        assert query == "python range stop value explained"
        return CANDIDATES

    monkeypatch.setattr(agent, "search", fake_search)
    result = await agent.find_video(CONTEXT, "Think about where counting starts.")

    assert result["kind"] == "embed"
    assert result["video_id"] == "BBB"
    assert result["reason"] == "It shows why range stops before 5."
    assert result["source"] == "api"


async def test_without_the_model_it_takes_the_top_result(monkeypatch, memory_cache, model,
                                                          api_key):
    async def fake_search(query, key):
        assert query == "Python loops for and range explained"
        return CANDIDATES

    monkeypatch.setattr(agent, "search", fake_search)
    result = await agent.find_video(CONTEXT)
    assert result["video_id"] == "AAA"


async def test_a_failed_query_step_skips_the_choose_step(monkeypatch, memory_cache, api_key):
    """No second model call once the model has failed: two step timeouts plus the search would
    overrun the request budget and lose a video that was available."""
    asks = []

    async def fake_ask(system, human, timeout_s=None):
        asks.append(system)
        return None

    async def fake_search(query, key):
        return CANDIDATES

    monkeypatch.setattr(agent, "_ask", fake_ask)
    monkeypatch.setattr(agent, "search", fake_search)
    result = await agent.find_video(CONTEXT)
    assert result["kind"] == "embed" and result["video_id"] == "AAA"
    assert len(asks) == 1


async def test_a_model_naming_an_unlisted_video_falls_back(monkeypatch, memory_cache, model,
                                                           api_key):
    model.extend([{"query": "q q q q", "concept": "c"}, {"video_id": "ZZZ", "reason": "x"}])

    async def fake_search(query, key):
        return CANDIDATES

    monkeypatch.setattr(agent, "search", fake_search)
    assert (await agent.find_video(CONTEXT))["video_id"] == "AAA"


async def test_a_cached_result_skips_the_search(monkeypatch, memory_cache, model, api_key):
    calls = []

    async def fake_search(query, key):
        calls.append(query)
        return CANDIDATES

    monkeypatch.setattr(agent, "search", fake_search)
    first = await agent.find_video(CONTEXT)
    second = await agent.find_video(CONTEXT)

    assert len(calls) == 1
    assert second["video_id"] == first["video_id"]
    assert second["source"] == "cache"


async def test_no_api_key_gives_a_search_link(monkeypatch, memory_cache, model):
    monkeypatch.setattr(settings, "YOUTUBE_API_KEY", "")
    result = await agent.find_video(CONTEXT)
    assert result["kind"] == "link"
    assert result["url"].startswith("https://www.youtube.com/results?search_query=")


async def test_a_search_failure_gives_a_search_link(monkeypatch, memory_cache, model, api_key):
    async def broken(query, key):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(agent, "search", broken)
    result = await agent.find_video(CONTEXT)
    assert result["kind"] == "link"


async def test_no_candidates_gives_a_search_link(monkeypatch, memory_cache, model, api_key):
    async def empty(query, key):
        return []

    monkeypatch.setattr(agent, "search", empty)
    assert (await agent.find_video(CONTEXT))["kind"] == "link"


async def test_it_never_raises(monkeypatch, model, api_key):
    async def exploding_cache(key):
        raise RuntimeError("redis down")

    monkeypatch.setattr(redis_service, "get_json", exploding_cache)
    result = await agent.find_video(CONTEXT)
    assert result["kind"] == "link"
    assert result["source"] == "fallback"


async def test_search_keeps_only_lesson_length_embeddable_videos(monkeypatch):
    class Resp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            if url.endswith("/search"):
                return Resp({"items": [{"id": {"videoId": v}} for v in ("A", "B", "C", "D")]})
            return Resp({"items": [
                {"id": "A", "contentDetails": {"duration": "PT5M"}, "status": {"embeddable": True},
                 "snippet": {"title": "ok", "channelTitle": "c"}},
                {"id": "B", "contentDetails": {"duration": "PT40S"}, "status": {},
                 "snippet": {}},
                {"id": "C", "contentDetails": {"duration": "PT2H"}, "status": {}, "snippet": {}},
                {"id": "D", "contentDetails": {"duration": "PT3M"},
                 "status": {"embeddable": False}, "snippet": {}},
            ]})

    monkeypatch.setattr(agent.httpx, "AsyncClient", Client)
    out = await agent.search("q", "k")
    assert [c["video_id"] for c in out] == ["A"]
