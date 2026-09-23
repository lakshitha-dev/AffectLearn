"""The escalation ladder: the thing that makes this system adaptive rather than merely reactive.

Before this, `_RULE_MAP` held ONE action per state, so a learner confused three times in the same
section received `show_hint` three times. That is not a weak adaptive policy — it is the absence of
one, and it makes the study's central question unanswerable, because nothing ever varied in
response to the intervention having failed.

Two properties carry the design and both fail silently:

  * The rung must be read BEFORE it is advanced, or every learner opens one rung deep and the
    first rung of every ladder is dead code.
  * The rung must advance on DELIVERY only. A withheld cycle showed the learner nothing, so
    nothing was tried; advancing there would skip rungs the learner never saw, and it would do so
    in the control arm's shadow where no one would look for it.
"""

from __future__ import annotations

import pytest

from app.agents.edges import (
    current_rung,
    record_delivered_rung,
)
from app.agents.fallbacks import ladder_for, rule_based_strategy


# ── the ladders themselves ────────────────────────────────────────────────────────────

def test_confusion_escalates_from_cheapest_to_most_invasive():
    """Ordered by cost to the learner.

    Confusion that resolves on its own is the kind that teaches (D'Mello et al. 2014), so opening
    with a full re-explanation spends a real learning opportunity. A hint asks the learner to
    think again; a breakdown does some of the thinking; an alternative replaces their framing.
    """
    assert [ladder_for("confused", i)[0] for i in range(3)] == [
        "show_hint",
        "show_breakdown",
        "show_alternative",
    ]


def test_boredom_raises_challenge_before_conceding_the_material():
    """Flow theory places boredom at challenge BELOW skill, so the first move is to raise it."""
    assert [ladder_for("bored", i)[0] for i in range(2)] == ["increase_difficulty", "skip_ahead"]


def test_frustration_ends_in_withdrawal_which_the_others_do_not():
    assert [ladder_for("frustrated", i)[0] for i in range(3)] == [
        "show_encouragement",
        "simplify",
        "suggest_break",
    ]


def test_engaged_never_escalates_into_an_intervention():
    """`engaged` is not in ADAPT_STATES; if it somehow routes here it must stay a no-op."""
    assert all(ladder_for("engaged", i)[0] == "no_action" for i in range(5))


def test_the_ladder_clamps_rather_than_wrapping():
    """Cycling back to a hint the learner already dismissed would be worse than repeating the
    deepest rung, and there is nothing past a video walkthrough this system can deliver."""
    deepest = ladder_for("confused", 3)
    assert deepest[0] == "show_video"
    assert ladder_for("confused", 99) == deepest


def test_an_unknown_state_is_safe():
    assert ladder_for("elated", 0) == ("no_action", "low")
    assert ladder_for(None, 3) == ("no_action", "low")


def test_the_rule_based_strategy_uses_the_rung():
    """The fallback path is the DETERMINISTIC one, so it is the path that must escalate.

    It runs whenever the LLM times out, errors or returns unparseable output — and on a degraded
    provider that is every cycle, which is exactly when a stuck policy would go unnoticed.
    """
    assert rule_based_strategy("confused", {}, 0)["action_type"] == "show_hint"
    assert rule_based_strategy("confused", {}, 1)["action_type"] == "show_breakdown"
    assert rule_based_strategy("confused", {}, 2)["action_type"] == "show_alternative"


# ── rung bookkeeping ──────────────────────────────────────────────────────────────────

def test_a_fresh_learner_starts_at_the_first_rung():
    assert current_rung({}, "S1", "sec1", "confused") == 0


def test_each_delivery_advances_the_ladder():
    profile: dict = {}
    seen = []
    for _ in range(3):
        seen.append(ladder_for("confused", current_rung(profile, "S1", "sec1", "confused"))[0])
        record_delivered_rung(profile, "S1", "sec1", "confused")

    assert seen == ["show_hint", "show_breakdown", "show_alternative"]


def test_rungs_are_tracked_per_section():
    """A learner confused by recursion and later confused by a different section are two
    independent situations. Carrying the rung across would open the second at the heaviest
    intervention, on material they have not yet struggled with."""
    profile: dict = {}
    record_delivered_rung(profile, "S1", "sec1", "confused")
    record_delivered_rung(profile, "S1", "sec1", "confused")

    assert current_rung(profile, "S1", "sec1", "confused") == 2
    assert current_rung(profile, "S1", "sec2", "confused") == 0


def test_rungs_are_tracked_per_state():
    """Boredom and confusion are different ladders; progress on one says nothing about the other."""
    profile: dict = {}
    record_delivered_rung(profile, "S1", "sec1", "confused")

    assert current_rung(profile, "S1", "sec1", "bored") == 0


def test_a_new_session_starts_the_ladder_over():
    """Same class of bug the cooldown marker carries a session stamp for: a rung carried in from
    an earlier session would open a fresh one at the deepest intervention."""
    profile: dict = {}
    for _ in range(3):
        record_delivered_rung(profile, "S1", "sec1", "confused")

    assert current_rung(profile, "S2", "sec1", "confused") == 0


def test_a_corrupt_rung_store_does_not_crash_the_gate():
    """The profile round-trips through Redis and Postgres; a bad value must degrade, not raise."""
    assert current_rung({"adaptation_session_id": "S1", "ladder_rungs": "junk"},
                        "S1", "sec1", "confused") == 0

    profile = {"adaptation_session_id": "S1", "ladder_rungs": "junk"}
    record_delivered_rung(profile, "S1", "sec1", "confused")
    assert profile["ladder_rungs"] == {"sec1|confused": 1}


def test_a_missing_section_still_tracks_a_ladder():
    """`content_context` can be absent — the learner still gets escalation, just session-wide."""
    profile: dict = {}
    record_delivered_rung(profile, "S1", None, "confused")
    assert current_rung(profile, "S1", None, "confused") == 1


# ── the interaction with the trial arms ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_withheld_cycle_does_not_advance_the_ladder(monkeypatch):
    """The property that keeps the ladder meaningful.

    A withheld cycle delivered nothing, so nothing was tried and nothing was ruled out. If it
    advanced the rung, a learner in the withheld arm could reach `show_alternative` having never
    seen a hint — and the delivered arm's rung distribution would then depend on coin flips rather
    than on what the learner actually received.
    """
    import app.agents.nodes.learner_profiler as lp
    from app.agents import edges
    from app.agents.state import make_initial_state

    events: list[dict] = []

    async def fake_emit(e):
        events.append(e)

    monkeypatch.setattr(lp, "emit_research_event", fake_emit)

    async def fake_get(key):
        return {
            "affect_state": "confused", "affect_history": ["confused", "confused"],
            "affect_history_by_source": {"behavioral_model": ["confused", "confused"]},
            "skill_level": "intermediate", "topic_mastery": {}, "format_preferences": {},
            "session_count": 0, "cycle_count": 3, "updated_at": 1,
        }

    async def fake_set(key, value, ttl_seconds=None):
        return None

    monkeypatch.setattr(lp.redis_service, "get_json", fake_get)
    monkeypatch.setattr(lp.redis_service, "set_json", fake_set)
    monkeypatch.setattr(edges, "ADAPT_WITHHOLD_RATE", 1.0)      # withhold everything

    state = make_initial_state(learner_id="u1", session_id="s1", cycle_number=9)
    state.update({
        "affect_state": "confused", "affect_confidence": 0.95,
        "affect_source": "behavioral_model", "phase": "phase_b", "group": "adaptive",
        "content_context": {"section_id": "sec1"},
    })

    out = await lp.learner_profiler_node(state)

    assert out["adaptation_gate_reason"] == "withheld_random"
    assert out["ladder_rung"] == 0
    # Nothing was shown, so the next DELIVERED intervention must still be the first rung.
    assert current_rung(out["learner_profile"], "s1", "sec1", "confused") == 0
