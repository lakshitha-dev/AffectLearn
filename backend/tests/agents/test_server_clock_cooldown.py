"""The cooldown is measured on the server clock, not on client cycle numbers.

Client `cycle_number` values are not a clock. Each channel's hook keeps its own counter, and every
counter restarts at 1 when the lesson page remounts, while the platform session -- and the cooldown
marker stamped in it -- carries on. Subtracting them held a new lesson in `cooldown` until its
counter climbed back past the old marker (an offer at cycle 40 silenced the next lesson for about
20 minutes), and two channels whose counters started at different moments disagreed about the
cooldown even inside one lesson.
"""

import pytest

import app.agents.nodes.learner_profiler as lp
from app.agents import edges
from app.agents.edges import (
    GATE_COOLDOWN,
    GATE_OK,
    adaptation_decision,
    commit_offer,
    cycles_since_offer,
    stamp_offer,
)
from app.agents.state import make_initial_state

CYCLE_MS = 30_000


class TestCyclesSinceOffer:
    def test_none_before_any_offer(self):
        assert cycles_since_offer({}, "s1", 10 * CYCLE_MS) is None

    def test_a_marker_from_another_session_is_ignored(self):
        p: dict = {}
        stamp_offer(p, "OLD", 0)
        assert cycles_since_offer(p, "NEW", CYCLE_MS) is None

    def test_whole_cycles_elapsed(self):
        p: dict = {}
        stamp_offer(p, "s1", 1_000)
        assert cycles_since_offer(p, "s1", 1_000 + 3 * CYCLE_MS) == 3

    def test_jitter_rounds_to_the_nearest_cycle(self):
        """The third window after an offer lands a little before or after the 90 s mark."""
        p: dict = {}
        stamp_offer(p, "s1", 0)
        assert cycles_since_offer(p, "s1", 3 * CYCLE_MS - 400) == 3
        assert cycles_since_offer(p, "s1", 3 * CYCLE_MS + 400) == 3

    def test_clock_skew_never_goes_negative(self):
        p: dict = {}
        stamp_offer(p, "s1", 10 * CYCLE_MS)
        assert cycles_since_offer(p, "s1", 0) == 0

    def test_stamping_drops_the_old_cycle_number_marker(self):
        p = {"last_adaptation_cycle": 40}
        stamp_offer(p, "s1", 0)
        assert "last_adaptation_cycle" not in p


def _eligible_state(cycle_number: int) -> dict:
    s = make_initial_state(learner_id="u1", session_id="s1", cycle_number=cycle_number)
    s.update({"affect_state": "bored", "affect_confidence": 0.95,
              "affect_source": "facial_geometry", "phase": "phase_b", "group": "adaptive"})
    return s


def _sustained_profile() -> dict:
    return {"affect_history": ["bored", "bored"],
            "affect_history_by_source": {"facial_geometry": ["bored", "bored"]}}


class TestAcrossAClientCounterReset:
    """An offer late in one lesson, then the page remounts and the client counter restarts."""

    def test_the_new_lesson_is_not_held_by_the_old_counter(self, monkeypatch):
        monkeypatch.setattr(edges, "ADAPT_WITHHOLD_RATE", 0.0)
        profile = _sustained_profile()
        commit_offer(profile, {"gate_reason": GATE_OK, "session_id": "s1",
                               "section_id": "sec-A", "affect_state": "bored"}, now_ms=0)

        # Four cycles (2 min) later, in a new lesson whose client counter restarted at 1. The old
        # arithmetic, 1 - 40, would have read as "still in cooldown" until cycle 43.
        since = cycles_since_offer(profile, "s1", 4 * CYCLE_MS)
        allowed, reason = adaptation_decision(
            _eligible_state(cycle_number=1), profile, None, cycles_since_last_offer=since
        )
        assert (allowed, reason) == (True, GATE_OK)

    def test_the_cooldown_still_holds_straight_after_an_offer(self, monkeypatch):
        monkeypatch.setattr(edges, "ADAPT_WITHHOLD_RATE", 0.0)
        profile = _sustained_profile()
        commit_offer(profile, {"gate_reason": GATE_OK, "session_id": "s1",
                               "section_id": "sec-A", "affect_state": "bored"}, now_ms=0)

        # One cycle later, even though the (reset) client counter says 1 and the marker's lesson
        # reached 40: time, not the counter, decides.
        since = cycles_since_offer(profile, "s1", 1 * CYCLE_MS)
        allowed, reason = adaptation_decision(
            _eligible_state(cycle_number=1), profile, None, cycles_since_last_offer=since
        )
        assert (allowed, reason) == (False, GATE_COOLDOWN)

    def test_cycle_number_arithmetic_is_kept_for_direct_callers(self):
        """Callers that pass no server-clock reading keep the old contract unchanged."""
        profile = _sustained_profile()
        allowed, reason = adaptation_decision(_eligible_state(cycle_number=6), profile, 5)
        assert (allowed, reason) == (False, GATE_COOLDOWN)


@pytest.mark.asyncio
async def test_the_profiler_reads_the_cooldown_from_the_server_clock(monkeypatch):
    """End to end through the node: the reset counter no longer matters, the clock does."""
    from app.services import config_service

    stored = {"value": {**_sustained_profile(), "last_adaptation_ms": 0,
                        "last_adaptation_session": "s1", "cycle_count": 50}}

    async def get_json(key):
        return dict(stored["value"])

    async def set_json(key, value, ttl_seconds=None):
        stored["value"] = value

    async def no_emit(event):
        return None

    monkeypatch.setattr(lp.redis_service, "get_json", get_json)
    monkeypatch.setattr(lp.redis_service, "set_json", set_json)
    monkeypatch.setattr(lp, "emit_research_event", no_emit)
    monkeypatch.setattr(edges, "ADAPT_WITHHOLD_RATE", 0.0)
    config_service._reset()

    monkeypatch.setattr(lp, "_clock_ms", lambda: 1 * CYCLE_MS)
    out = await lp.learner_profiler_node(_eligible_state(cycle_number=1))
    assert out["adaptation_gate_reason"] == GATE_COOLDOWN

    monkeypatch.setattr(lp, "_clock_ms", lambda: 3 * CYCLE_MS)
    out = await lp.learner_profiler_node(_eligible_state(cycle_number=2))
    assert out["adaptation_gate_reason"] == GATE_OK
