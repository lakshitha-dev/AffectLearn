"""Tests for the Learner Profiler node (Story 4.5 AC4)."""

import pytest

import app.agents.nodes.learner_profiler as lp
from app.agents.state import make_initial_state

pytestmark = pytest.mark.asyncio


@pytest.fixture
def profile_events(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(lp, "emit_research_event", fake_emit)
    return events


def _patch_redis(monkeypatch, get_value):
    stored: dict = {}

    async def fake_get(key):
        return get_value

    async def fake_set(key, value, ttl_seconds=None):
        stored["key"] = key
        stored["value"] = value

    monkeypatch.setattr(lp.redis_service, "get_json", fake_get)
    monkeypatch.setattr(lp.redis_service, "set_json", fake_set)
    return stored


async def test_redis_miss_no_db_uses_default(monkeypatch, profile_events):
    _patch_redis(monkeypatch, get_value=None)
    state = make_initial_state(learner_id="u1", session_id="s1", cycle_number=1)
    state["affect_state"] = "confused"

    out = await lp.learner_profiler_node(state)
    prof = out["learner_profile"]
    assert prof["affect_state"] == "confused"
    assert prof["affect_history"] == ["confused"]
    assert "should_adapt" in out
    assert profile_events[0]["event_type"] == "learner_profile_updated"
    assert profile_events[0]["payload"]["source"] == "default"


async def test_redis_hit_updates_and_writes_through(monkeypatch, profile_events):
    hot = {"affect_state": "engaged", "affect_history": ["engaged"], "skill_level": "advanced",
           "topic_mastery": {}, "format_preferences": {}, "session_count": 0,
           "cycle_count": 3, "updated_at": 1}
    stored = _patch_redis(monkeypatch, get_value=hot)
    state = make_initial_state(learner_id="u1", session_id="s1", cycle_number=4)
    state["affect_state"] = "bored"

    out = await lp.learner_profiler_node(state)
    prof = out["learner_profile"]
    assert prof["skill_level"] == "advanced"          # preserved from hot profile
    assert prof["affect_history"][-1] == "bored"
    assert prof["cycle_count"] == 4
    assert stored["value"]["affect_state"] == "bored"  # write-through to Redis
    assert profile_events[0]["payload"]["source"] == "redis"


async def test_redis_get_raises_is_swallowed(monkeypatch, profile_events):
    async def boom(key):
        raise RuntimeError("redis down")

    async def fake_set(key, value, ttl_seconds=None):
        pass

    monkeypatch.setattr(lp.redis_service, "get_json", boom)
    monkeypatch.setattr(lp.redis_service, "set_json", fake_set)
    state = make_initial_state(learner_id="u1", session_id="s1", cycle_number=1)
    state["affect_state"] = "engaged"

    out = await lp.learner_profiler_node(state)   # must not raise (NFR22)
    assert out["learner_profile"]["affect_state"] == "engaged"


async def test_cold_persist_gated_to_interval(monkeypatch, profile_events, db, test_user):
    """M1: Postgres is written only every Nth cycle, not every cycle."""
    from app.services.profile_service import default_profile

    persisted: list[int] = []

    async def fake_persist(_db, _uid, prof):
        persisted.append(prof["cycle_count"])

    async def fake_set(key, value, ttl_seconds=None):
        pass

    monkeypatch.setattr(lp.profile_service, "persist_cold", fake_persist)
    monkeypatch.setattr(lp.redis_service, "set_json", fake_set)

    state = make_initial_state(learner_id=str(test_user.id), session_id="s1", cycle_number=10, db=db)
    state["affect_state"] = "engaged"

    async def get_count_9(key):
        return {**default_profile(), "cycle_count": 9}     # -> 10 after apply -> persists

    monkeypatch.setattr(lp.redis_service, "get_json", get_count_9)
    await lp.learner_profiler_node(state)
    assert persisted == [10]

    persisted.clear()

    async def get_count_7(key):
        return {**default_profile(), "cycle_count": 7}     # -> 8 -> no persist

    monkeypatch.setattr(lp.redis_service, "get_json", get_count_7)
    await lp.learner_profiler_node(state)
    assert persisted == []


async def test_cold_path_used_on_redis_miss_with_db(monkeypatch, profile_events, db, test_user):
    from app.services import profile_service as ps
    await ps.persist_cold(db, test_user.id, {**ps.default_profile(), "skill_level": "low"})
    _patch_redis(monkeypatch, get_value=None)

    state = make_initial_state(learner_id=str(test_user.id), session_id="s1", cycle_number=1, db=db)
    state["affect_state"] = "frustrated"

    out = await lp.learner_profiler_node(state)
    prof = out["learner_profile"]
    assert prof["skill_level"] == "low"             # came from the cold store
    assert prof["affect_history"] == ["frustrated"]
    assert profile_events[0]["payload"]["source"] == "postgres_or_init"
