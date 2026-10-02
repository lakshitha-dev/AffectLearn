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


# ── randomised trial: the arms must stay matched through the profiler ─────────────────

async def _run_gated_cycle(monkeypatch, profile_events, *, rate, cycle, session="s1"):
    """Drive one cycle that clears every gate condition, at the given withhold rate."""
    from app.agents import edges

    _patch_redis(monkeypatch, get_value={
        "affect_state": "bored", "affect_history": ["bored", "bored"],
        "affect_history_by_source": {"facial_geometry": ["bored", "bored"]},
        "skill_level": "intermediate", "topic_mastery": {}, "format_preferences": {},
        "session_count": 0, "cycle_count": 3, "updated_at": 1,
    })
    state = make_initial_state(learner_id="u1", session_id=session, cycle_number=cycle)
    state.update({
        "affect_state": "bored", "affect_confidence": 0.95,
        "affect_source": "facial_geometry", "phase": "phase_b", "group": "adaptive",
    })
    monkeypatch.setattr(edges, "ADAPT_WITHHOLD_RATE", rate)
    # The node reads the CACHED config, so the patched constant only takes effect once the cache
    # is rebuilt from it. Without this the patch would silently not apply.
    from app.services import config_service
    config_service._reset()

    out = await lp.learner_profiler_node(state)
    return out, profile_events[-1]["payload"]


async def test_a_withheld_cycle_still_spends_the_cooldown(monkeypatch, profile_events):
    """The property the whole comparison rests on.

    A withheld cycle cleared every gate condition; it is the control observation. If it did not
    spend the cooldown, the control arm would become eligible again sooner than the delivered
    arm, drift to a higher trigger rate, and stop being matched to it -- and nothing downstream
    could detect that had happened. It is complete at the gate, so it spends it there.
    """
    out, payload = await _run_gated_cycle(monkeypatch, profile_events, rate=1.0, cycle=9)

    assert out["should_adapt"] is False
    assert out["adaptation_gate_reason"] == "withheld_random"
    assert payload["arm"] == "withheld"
    prof = out["learner_profile"]
    assert prof["last_adaptation_session"] == "s1"
    assert isinstance(prof["last_adaptation_ms"], int)
    assert prof["eligible_this_session"] == 1
    # Nothing was shown, so nothing was tried: the ladder does not move, and nothing is carried
    # forward to the socket handler.
    assert not prof.get("ladder_rungs")
    assert out["offer_commit"] is None


async def test_a_passing_cycle_spends_nothing_until_its_card_is_delivered(
    monkeypatch, profile_events
):
    """The strategist may still choose no_action, or the card may be dropped: nothing is spent yet.

    The cost is carried forward instead, and spent by the socket handler after a successful send.
    """
    out, payload = await _run_gated_cycle(monkeypatch, profile_events, rate=0.0, cycle=9)

    assert out["should_adapt"] is True
    assert payload["arm"] == "delivered"
    prof = out["learner_profile"]
    assert "last_adaptation_ms" not in prof
    assert not prof.get("eligible_this_session")
    assert not prof.get("ladder_rungs")
    assert out["offer_commit"] == {
        "gate_reason": "ok", "session_id": "s1", "section_id": None, "affect_state": "bored",
    }


async def test_a_cycle_that_failed_the_gate_spends_nothing(monkeypatch, profile_events):
    """Only cycles that reached the trial spend the window; a rejected one costs the learner nothing."""
    _patch_redis(monkeypatch, get_value=None)
    state = make_initial_state(learner_id="u1", session_id="s1", cycle_number=4)
    state.update({
        "affect_state": "bored", "affect_confidence": 0.10,   # under the geometry floor
        "affect_source": "facial_geometry", "phase": "phase_b", "group": "adaptive",
    })

    out = await lp.learner_profiler_node(state)

    assert out["adaptation_gate_reason"] == "low_confidence"
    assert profile_events[-1]["payload"]["arm"] is None
    assert "last_adaptation_ms" not in out["learner_profile"]
    assert out["offer_commit"] is None


# ── commit_delivered_offer: what a card costs once it reached the learner ─────────────

def _ok_offer(session="s1", section="sec1", state="bored"):
    return {"gate_reason": "ok", "session_id": session, "section_id": section,
            "affect_state": state}


async def test_a_delivered_card_spends_cooldown_cap_and_rung(monkeypatch):
    stored = _patch_redis(monkeypatch, get_value={"cycle_count": 3})

    assert await lp.commit_delivered_offer("u1", _ok_offer(), now_ms=1_000_000) is True

    prof = stored["value"]
    assert prof["last_adaptation_ms"] == 1_000_000
    assert prof["last_adaptation_session"] == "s1"
    assert prof["eligible_this_session"] == 1
    assert prof["ladder_rungs"] == {"sec1|bored": 1}


async def test_a_delivered_learner_request_advances_the_ladder_only(monkeypatch):
    stored = _patch_redis(monkeypatch, get_value={"cycle_count": 3})
    offer = {**_ok_offer(state="confused"), "gate_reason": "learner_request"}

    assert await lp.commit_delivered_offer("u1", offer, now_ms=1_000_000) is True

    prof = stored["value"]
    assert prof["ladder_rungs"] == {"sec1|confused": 1}
    assert "last_adaptation_ms" not in prof
    assert not prof.get("eligible_this_session")


async def test_no_offer_commits_nothing(monkeypatch):
    stored = _patch_redis(monkeypatch, get_value={"cycle_count": 3})

    assert await lp.commit_delivered_offer("u1", None) is False
    assert stored == {}


async def test_commit_never_raises(monkeypatch):
    async def boom(key):
        raise RuntimeError("redis down")

    monkeypatch.setattr(lp.redis_service, "get_json", boom)
    assert await lp.commit_delivered_offer("u1", _ok_offer()) is False
