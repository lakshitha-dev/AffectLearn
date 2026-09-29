"""The control arm's shadow gate: where the adaptive arm WOULD have offered help.

A between-group comparison of what follows an offer of help needs the matching moments in the
control arm, where nothing is offered. These tests pin that a Phase B control cycle records the
adaptive arm's verdict -- with its own persistence, cooldown and cap -- while the learner's real
gate counters, the delivery path and every other arm are left exactly as they were.
"""

import pytest

import app.agents.nodes.learner_profiler as lp
from app.agents import delivery_guard, edges
from app.agents.state import make_initial_state
from app.services import config_service

pytestmark = pytest.mark.asyncio

CYCLE_MS = 30_000


@pytest.fixture
def harness(monkeypatch):
    """A persistent in-memory profile store, a controllable clock, and the captured events."""
    store: dict = {}
    events: list[dict] = []
    clock = {"ms": 0}

    async def get_json(key):
        return store.get(key)

    async def set_json(key, value, ttl_seconds=None):
        store[key] = value

    async def emit(event):
        events.append(event)

    monkeypatch.setattr(lp.redis_service, "get_json", get_json)
    monkeypatch.setattr(lp.redis_service, "set_json", set_json)
    monkeypatch.setattr(lp, "emit_research_event", emit)
    monkeypatch.setattr(lp, "_clock_ms", lambda: clock["ms"])
    monkeypatch.setattr(delivery_guard, "SECTION_GRACE_MS", 0)
    monkeypatch.setattr(edges, "ADAPT_WITHHOLD_RATE", 0.0)
    config_service._reset()
    return store, events, clock


async def _cycle(harness, n, *, phase="phase_b", group="control", state="bored", conf=0.95):
    store, events, clock = harness
    clock["ms"] = n * CYCLE_MS
    s = make_initial_state(learner_id="u1", session_id="s1", cycle_number=n,
                           phase=phase, group=group,
                           content_context={"section_id": "sec-1"})
    s.update({"affect_state": state, "affect_confidence": conf,
              "affect_source": "facial_geometry"})
    out = await lp.learner_profiler_node(s)
    return out, events[-1]["payload"]


async def test_control_records_where_help_would_have_been_offered(harness):
    first, p1 = await _cycle(harness, 1)
    second, p2 = await _cycle(harness, 2)
    third, p3 = await _cycle(harness, 3)

    assert p1["shadow_gate"] == edges.GATE_NOT_SUSTAINED
    assert p2["shadow_gate"] == edges.GATE_OK and p2["shadow_would_offer"] is True
    assert p3["shadow_gate"] == edges.GATE_COOLDOWN and p3["shadow_would_offer"] is False
    # The learner's own gate is untouched: control is never eligible, nothing is offered.
    for out, payload in ((first, p1), (second, p2), (third, p3)):
        assert out["adaptation_gate_reason"] == edges.GATE_NOT_ELIGIBLE
        assert out["should_adapt"] is False and out["offer_commit"] is None
        assert payload["arm"] is None


async def test_the_shadow_spends_only_its_own_counters(harness):
    await _cycle(harness, 1)
    out, _ = await _cycle(harness, 2)
    profile = out["learner_profile"]
    for key in ("last_adaptation_ms", "eligible_this_session", "ladder_rungs"):
        assert key not in profile, key
    shadow = profile["shadow_gate"]
    assert shadow["last_adaptation_ms"] == 2 * CYCLE_MS
    assert shadow["eligible_this_session"] == 1
    assert shadow["ladder_rungs"] == {"sec-1|bored": 1}


async def test_the_shadow_cooldown_ends_like_the_adaptive_arms(harness):
    await _cycle(harness, 1)
    await _cycle(harness, 2)                       # would offer; cooldown starts
    verdicts = [(await _cycle(harness, n))[1]["shadow_gate"] for n in (3, 4, 5, 6)]
    assert verdicts[:2] == [edges.GATE_COOLDOWN, edges.GATE_COOLDOWN]
    assert edges.GATE_OK in verdicts[2:]


async def test_the_shadow_respects_the_confidence_floor(harness):
    await _cycle(harness, 1, conf=0.55)
    _, payload = await _cycle(harness, 2, conf=0.55)
    assert payload["shadow_gate"] == edges.GATE_LOW_CONFIDENCE


async def test_no_shadow_for_the_adaptive_arm_or_phase_a(harness):
    _, adaptive = await _cycle(harness, 1, group="adaptive")
    _, phase_a = await _cycle(harness, 2, phase="phase_a")
    assert adaptive["shadow_gate"] is None and adaptive["shadow_would_offer"] is None
    assert phase_a["shadow_gate"] is None


async def test_the_adaptive_arm_is_unchanged(harness):
    """Same readings, adaptive arm: offers on the second cycle, exactly as before."""
    await _cycle(harness, 1, group="adaptive")
    out, payload = await _cycle(harness, 2, group="adaptive")
    assert out["adaptation_gate_reason"] == edges.GATE_OK
    assert out["offer_commit"] is not None
    assert "shadow_gate" not in out["learner_profile"]
