"""Grounded hints and learner-requested help.

Two changes are covered here:

* The strategist and the content adapter now see what the learner DID in the section (wrong
  answers, a revealed answer, re-reading, time spent) and, for the strategist, an excerpt of the
  section itself. These tests pin that the evidence reaches the prompts and that an absent record
  leaves them unchanged.
* A learner can ask for the next step from a card ("Still stuck" / "I'd rather move on"). The gate
  passes such a request without the detector's restraints, but only on the adaptive arm; the
  ladder still advances; and the strategist may not answer the request with silence.
"""

from __future__ import annotations

import pytest

import app.agents.nodes.content_adapter as ca
import app.agents.nodes.pedagogical as ped
from app.agents import edges
from app.agents.state import AFFECT_SOURCE_LEARNER_REQUEST, make_initial_state
from app.services import learner_activity


# ── learner_activity.describe / attach ───────────────────────────────────────────────


def test_describe_states_observed_counts_only():
    line = learner_activity.describe({
        "quiz_incorrect_count": 2,
        "show_answer_used": True,
        "back_nav_count": 1,
        "time_on_section_s": 250,
    })
    assert "incorrectly 2 time(s)" in line
    assert "revealed the answer" in line
    assert "re-read 1 time(s)" in line
    assert "4 minute(s)" in line


def test_describe_is_empty_when_nothing_happened():
    assert learner_activity.describe({"time_on_section_s": 20}) == ""
    assert learner_activity.describe(None) == ""
    assert learner_activity.describe("junk") == ""


@pytest.mark.asyncio
async def test_attach_copies_rather_than_mutating_the_shared_context(monkeypatch):
    async def fake_get(learner_id, section_id):
        return {"quiz_incorrect_count": 3, "back_nav_count": 0,
                "show_answer_used": False, "time_on_section_s": 0.0}

    monkeypatch.setattr(learner_activity, "get", fake_get)
    shared = {"section_id": "s1", "topic": "loops"}
    attached = await learner_activity.attach(shared, "learner-1")

    assert attached["learner_activity"]["quiz_incorrect_count"] == 3
    # The cached dict another learner will read must be untouched.
    assert "learner_activity" not in shared


@pytest.mark.asyncio
async def test_attach_without_a_record_adds_nothing(monkeypatch):
    async def fake_get(learner_id, section_id):
        return None

    monkeypatch.setattr(learner_activity, "get", fake_get)
    attached = await learner_activity.attach({"section_id": "s1"}, "learner-1")
    assert "learner_activity" not in attached


# ── the evidence reaches both prompts ────────────────────────────────────────────────

_CONTEXT = {
    "section_id": "s1",
    "topic": "for loops",
    "difficulty": "beginner",
    "body": "A for loop repeats a block once for each item in a sequence. " * 20,
    "learner_activity": {"quiz_incorrect_count": 2, "back_nav_count": 0,
                         "show_answer_used": False, "time_on_section_s": 0.0},
}


def test_strategist_prompt_carries_excerpt_and_activity():
    prompt = ped._build_human_prompt("confused", 0.8, {}, _CONTEXT, 0)
    assert "section_excerpt: A for loop repeats" in prompt
    assert "learner_activity: answered this section's question incorrectly 2 time(s)" in prompt
    # An excerpt, not the whole body.
    assert len(prompt) < len(_CONTEXT["body"]) + 800


def test_strategist_prompt_marks_a_learner_request():
    assert "learner_requested: yes" in ped._build_human_prompt(
        "confused", 1.0, {}, _CONTEXT, 1, requested=True
    )
    assert "learner_requested" not in ped._build_human_prompt("confused", 1.0, {}, _CONTEXT, 1)


def test_strategist_prompt_without_activity_is_unchanged_in_shape():
    context = {k: v for k, v in _CONTEXT.items() if k != "learner_activity"}
    prompt = ped._build_human_prompt("confused", 0.8, {}, context, 0)
    assert "learner_activity" not in prompt


def test_adapter_prompt_targets_the_misconception_after_wrong_answers():
    prompt = ca._build_human_prompt("show_hint", {}, _CONTEXT)
    assert "What the learner has done in this section so far" in prompt
    assert "likely misconception" in prompt
    assert "do not reveal" in prompt.lower()


def test_adapter_prompt_without_wrong_answers_has_no_misconception_line():
    context = {**_CONTEXT, "learner_activity": {"back_nav_count": 2}}
    prompt = ca._build_human_prompt("show_hint", {}, context)
    assert "re-read 2 time(s)" in prompt
    assert "likely misconception" not in prompt


# ── the gate and a learner request ───────────────────────────────────────────────────


def _requested_state(group: str = "adaptive") -> dict:
    state = make_initial_state(
        learner_id="l1", session_id="s1", cycle_number=5,
        phase="phase_b", group=group, content_context={"section_id": "sec"},
    )
    state["affect_state"] = "confused"
    state["affect_confidence"] = 1.0
    state["affect_source"] = AFFECT_SOURCE_LEARNER_REQUEST
    return state


def test_a_request_passes_without_the_detector_restraints():
    # A cooldown that would block any detected cycle, and no sustain history at all.
    allowed, reason = edges.adaptation_decision(_requested_state(), {}, last_adaptation_cycle=5)
    assert allowed is True
    assert reason == edges.GATE_LEARNER_REQUEST


def test_a_request_from_the_control_arm_is_still_not_eligible():
    allowed, reason = edges.adaptation_decision(_requested_state("control"), {}, None)
    assert allowed is False
    assert reason == edges.GATE_NOT_ELIGIBLE


def test_a_request_is_in_neither_trial_arm_and_spends_no_cooldown():
    assert edges.arm_for(edges.GATE_LEARNER_REQUEST) is None
    assert edges.consumes_cooldown(edges.GATE_LEARNER_REQUEST) is False


# ── the strategist may not answer a request with silence ─────────────────────────────


def test_no_action_on_a_request_becomes_the_ladder_rung():
    strategy = {"action_type": "no_action", "reason": "", "urgency": "low", "fallback": False}
    out = ped._honour_request(strategy, _requested_state(), rung=1)
    assert out["action_type"] == "show_breakdown"
    assert out["escalation_enforced"] is True
    assert out["model_action_type"] == "no_action"


def test_a_real_choice_on_a_request_is_left_alone():
    strategy = {"action_type": "show_alternative", "reason": "", "urgency": "high",
                "fallback": False}
    assert ped._honour_request(strategy, _requested_state(), rung=0) == strategy


def test_no_action_on_a_detected_cycle_is_left_alone():
    state = _requested_state()
    state["affect_source"] = "facial_geometry"
    strategy = {"action_type": "no_action", "reason": "", "urgency": "low", "fallback": False}
    assert ped._honour_request(strategy, state, rung=0) == strategy


# ── the same words twice in one section are not sent ────────────────────────────────


@pytest.mark.asyncio
async def test_identical_fallback_text_is_not_sent_twice(monkeypatch):
    from app.agents import fallbacks

    copy = fallbacks.rule_based_content("show_hint")["text"]

    async def already(state):
        return [copy]

    def no_model():
        raise RuntimeError("model unavailable")

    async def quiet(event):
        pass

    monkeypatch.setattr(ca, "_previously_shown", already)
    monkeypatch.setattr(ca, "get_chat_client", no_model)
    monkeypatch.setattr(ca, "emit_research_event", quiet)

    state = make_initial_state(learner_id="l1", session_id="s1", cycle_number=3,
                               phase="phase_b", group="adaptive",
                               content_context={"section_id": "sec"})
    state["strategy"] = {"action_type": "show_hint"}
    state["affect_state"] = "confused"
    assert await ca.content_adapter_node(state) == {}
