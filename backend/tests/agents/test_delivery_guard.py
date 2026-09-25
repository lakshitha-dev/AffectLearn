"""The delivery guard: what is on the learner's screen decides whether automatic help may interrupt.

Each test is one situation a learner would notice if the guard got it wrong.
"""

from __future__ import annotations

from app.agents import delivery_guard as g
from app.agents import edges
from app.agents.state import AFFECT_SOURCE_LEARNER_REQUEST, make_initial_state

NOW = 10_000_000
SEC = "section-A"


def _on(section=SEC, **extra):
    """A learner who arrived on `section` long enough ago that no grace period applies."""
    return {"section_id": section, "entered_ms": NOW - 10 * 60_000, **extra}


def check(ui, section=SEC, affect="confused", rungs=0, now=NOW):
    return g.blocked_reason(ui, now_ms=now, section_id=section, affect_state=affect, rungs_used=rungs)


# ── the holds ────────────────────────────────────────────────────────────────────────


def test_no_screen_state_means_no_holds():
    """An older client that sends no UI events behaves exactly as before."""
    assert check({}) is None
    assert check(None) is None


def test_a_settled_learner_with_nothing_on_screen_may_be_helped():
    assert check(_on()) is None


def test_a_reading_about_a_section_the_learner_left_is_stale():
    assert check(_on(section="section-B"), section=SEC) == g.GATE_STALE_SECTION


def test_a_hidden_tab_is_never_interrupted():
    assert check(_on(page_hidden=True)) == g.GATE_PAGE_HIDDEN


def test_an_open_card_is_not_replaced_while_it_is_being_read():
    ui = g.on_delivery(_on(), adaptation_id="a1", action="show_breakdown", section_id=SEC, now_ms=NOW)
    assert check(ui, now=NOW + 60_000) == g.GATE_CARD_OPEN
    # ...but a card nobody answered does not block forever.
    assert check(ui, now=NOW + g.TEXT_CARD_HOLD_MS + 1) is None


def test_a_video_holds_for_its_whole_length():
    ui = g.on_delivery(_on(), adaptation_id="v1", action="show_video", section_id=SEC, now_ms=NOW)
    assert check(ui, now=NOW + 10 * 60_000) == g.GATE_CARD_OPEN
    closed = g.on_video(ui, opened=False, adaptation_id=None, now_ms=NOW + 11 * 60_000)
    assert check(closed, now=NOW + 11 * 60_000) is None


def test_a_video_opened_from_a_hint_card_holds_too():
    ui = g.on_video(_on(), opened=True, adaptation_id="h1", now_ms=NOW)
    assert check(ui, now=NOW + 5 * 60_000) == g.GATE_CARD_OPEN


def test_arriving_on_a_new_section_gives_a_grace_period_and_clears_the_card():
    ui = g.on_delivery(_on(), adaptation_id="a1", action="show_hint", section_id=SEC, now_ms=NOW)
    moved = g.on_section_entered(ui, "section-B", NOW + 1_000)
    assert moved["open_card"] is None
    assert check(moved, section="section-B", now=NOW + 20_000) == g.GATE_SECTION_GRACE
    # Past the grace period and the minimum spacing since the last card, help may come again.
    assert check(moved, section="section-B", now=NOW + g.MIN_SPACING_MS + 1) is None


def test_re_entering_the_same_section_does_not_restart_the_grace_period():
    ui = _on()
    assert g.on_section_entered(ui, SEC, NOW) == ui


def test_answering_a_question_is_not_interrupted():
    ui = g.on_quiz_activity(_on(), NOW)
    assert check(ui, now=NOW + 10_000) == g.GATE_QUIZ_ACTIVE
    assert check(ui, now=NOW + g.QUIZ_HOLD_MS + 1) is None


def test_two_automatic_cards_are_spaced_apart():
    ui = g.on_delivery(_on(), adaptation_id="a1", action="show_hint", section_id=SEC, now_ms=NOW)
    answered = g.on_interaction(ui, interaction="requested", action="show_hint", section_id=SEC,
                                now_ms=NOW + 5_000)
    assert check(answered, now=NOW + 20_000) == g.GATE_RECENT_HELP
    assert check(answered, now=NOW + g.MIN_SPACING_MS + 1) is None


def test_got_it_leaves_that_state_alone_in_that_section():
    ui = g.on_interaction(_on(), interaction="accepted", action="show_hint", section_id=SEC,
                          now_ms=NOW)
    later = NOW + g.MIN_SPACING_MS + 1
    assert check(ui, affect="confused", now=later) == g.GATE_RESOLVED
    # A different state, or another section, is unaffected.
    assert check(ui, affect="bored", now=later) is None
    assert check({**ui, "section_id": "section-B"}, section="section-B", now=later) is None
    assert check(ui, affect="confused", now=NOW + g.RESOLVED_HOLD_MS + 1) is None


def test_not_now_waits_longer_and_does_not_count_as_a_rung():
    ui = g.on_interaction(_on(), interaction="dismissed", action="show_breakdown", section_id=SEC,
                          now_ms=NOW)
    assert check(ui, now=NOW + 100_000) == g.GATE_RECENT_HELP
    assert check(ui, now=NOW + g.DISMISS_HOLD_MS + 1) is None
    assert g.rung_credit(ui, SEC, "confused") == 1


def test_an_exhausted_ladder_stops_automatic_help():
    assert check(_on(), affect="confused", rungs=4) == g.GATE_LADDER_EXHAUSTED
    assert check(_on(), affect="bored", rungs=2) == g.GATE_LADDER_EXHAUSTED
    assert check(_on(), affect="bored", rungs=1) is None


def test_actions_map_to_their_ladder():
    assert g.state_for_action("show_video") == "confused"
    assert g.state_for_action("skip_ahead") == "bored"
    assert g.state_for_action("nonsense") is None


# ── the guard inside the gate ────────────────────────────────────────────────────────


def _detected(ui, affect="bored"):
    state = make_initial_state(
        learner_id="l1", session_id="s1", cycle_number=9, phase="phase_b", group="adaptive",
        content_context={"section_id": SEC}, ui_state=ui,
    )
    state["affect_state"] = affect
    state["affect_confidence"] = 0.95
    state["affect_source"] = "facial_geometry"
    return state


def _sustained_profile():
    return {"affect_history_by_source": {"facial_geometry": ["bored", "bored", "bored"]}}


def test_the_gate_withholds_a_detected_cycle_while_a_card_is_open():
    import time

    now = int(time.time() * 1000)
    ui = g.on_delivery({"section_id": SEC, "entered_ms": now - 600_000},
                       adaptation_id="a1", action="increase_difficulty", section_id=SEC, now_ms=now)
    allowed, reason = edges.adaptation_decision(_detected(ui), _sustained_profile(), None)
    assert allowed is False
    assert reason == g.GATE_CARD_OPEN


def test_a_learner_request_is_never_held():
    import time

    now = int(time.time() * 1000)
    ui = g.on_delivery({"section_id": SEC, "entered_ms": now},
                       adaptation_id="a1", action="show_hint", section_id=SEC, now_ms=now)
    state = _detected(ui, affect="confused")
    state["affect_source"] = AFFECT_SOURCE_LEARNER_REQUEST
    allowed, reason = edges.adaptation_decision(state, {}, None)
    assert allowed is True
    assert reason == edges.GATE_LEARNER_REQUEST


def test_every_hold_is_a_tracked_gate_reason():
    from app.services.monitor_aggregate_service import GATE_REASONS

    assert set(g.GUARD_REASONS) <= set(GATE_REASONS)
