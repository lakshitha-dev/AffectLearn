"""Tests for the Pedagogical Strategist node (Story 5.1 AC3/AC4/AC5).

vLLM is always mocked (no GPU): `get_chat_client` is monkeypatched to a fake client whose
`ainvoke` returns canned content, sleeps past the timeout, or raises.
"""

import asyncio

import pytest

import app.agents.llm as llm_mod
import app.agents.nodes.pedagogical as ped
from app.agents.state import make_initial_state
from app.core.config import settings

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def reset_llm_singleton():
    """Reset the vLLM client singleton before and after each test.

    Tests patch `ped.get_chat_client` directly so the singleton is never reached, but
    resetting it prevents a leaked real client from a future test that doesn't patch.
    """
    llm_mod._reset()
    yield
    llm_mod._reset()


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FakeClient:
    def __init__(self, *, content=None, exc=None, delay=0.0):
        self._content = content
        self._exc = exc
        self._delay = delay
        self.calls = 0

    async def ainvoke(self, messages):
        self.calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._exc:
            raise self._exc
        return _FakeResp(self._content)


@pytest.fixture
def events(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event):
        captured.append(event)

    monkeypatch.setattr(ped, "emit_research_event", fake_emit)
    return captured


def _use_client(monkeypatch, client):
    monkeypatch.setattr(ped, "get_chat_client", lambda: client)


def _state(affect="confused", **kw):
    state = make_initial_state(
        learner_id="u1", session_id="s1", cycle_number=1,
        phase="phase_b", group="adaptive", **kw,
    )
    if affect is not None:
        state["affect_state"] = affect
        state["affect_confidence"] = 0.82
        state["detection_mode"] = "facial_only"
    state["learner_profile"] = {"skill_level": "intermediate", "affect_history": ["confused"]}
    return state


async def test_success_uses_llm_strategy(monkeypatch, events):
    _use_client(monkeypatch, _FakeClient(
        content='{"action_type": "show_alternative", "reason": "sustained confusion", "urgency": "high"}'
    ))
    out = await ped.pedagogical_node(_state("confused"))
    strat = out["strategy"]
    assert strat["action_type"] == "show_alternative"
    assert strat["urgency"] == "high"
    assert strat["fallback"] is False
    assert events[0]["event_type"] == "strategy_decided"
    assert events[0]["payload"]["fallback"] is False


async def test_timeout_falls_back(monkeypatch, events):
    monkeypatch.setattr(settings, "VLLM_TIMEOUT_SECONDS", 0.05)
    _use_client(monkeypatch, _FakeClient(content="{}", delay=0.5))
    out = await ped.pedagogical_node(_state("confused"))
    strat = out["strategy"]
    assert strat["fallback"] is True
    assert strat["fallback_reason"] == "timeout"
    assert strat["action_type"] == "show_hint"        # confused -> rule-based hint
    assert events[0]["payload"]["fallback_reason"] == "timeout"


async def test_vllm_error_falls_back(monkeypatch, events):
    _use_client(monkeypatch, _FakeClient(exc=RuntimeError("connection refused")))
    out = await ped.pedagogical_node(_state("frustrated"))
    strat = out["strategy"]
    assert strat["fallback"] is True
    assert strat["fallback_reason"] == "vllm_error"
    # Rung 0 of the frustration ladder; `simplify` is now rung 1.
    assert strat["action_type"] == "show_encouragement"


async def test_unparseable_response_falls_back(monkeypatch, events):
    _use_client(monkeypatch, _FakeClient(content="I think you should take a break, friend!"))
    out = await ped.pedagogical_node(_state("bored"))
    strat = out["strategy"]
    assert strat["fallback"] is True
    assert strat["fallback_reason"] == "parse_error"
    # Rung 0 of the boredom ladder — raise challenge before conceding the material.
    assert strat["action_type"] == "increase_difficulty"


async def test_out_of_vocabulary_action_falls_back(monkeypatch, events):
    _use_client(monkeypatch, _FakeClient(
        content='{"action_type": "teleport_learner", "reason": "x", "urgency": "low"}'
    ))
    out = await ped.pedagogical_node(_state("engaged"))
    strat = out["strategy"]
    assert strat["fallback"] is True
    assert strat["fallback_reason"] == "parse_error"
    assert strat["action_type"] == "no_action"         # engaged -> rule-based no_action


async def test_no_affect_short_circuits_without_calling_llm(monkeypatch, events):
    def _boom():
        raise AssertionError("LLM must not be called when there is no affect_state")

    monkeypatch.setattr(ped, "get_chat_client", _boom)
    out = await ped.pedagogical_node(_state(affect=None))  # no affect_state set
    strat = out["strategy"]
    assert strat["action_type"] == "no_action"
    assert strat["fallback"] is True
    assert strat["fallback_reason"] == "no_affect"
    assert events[0]["payload"]["action_type"] == "no_action"


async def test_invalid_urgency_is_coerced(monkeypatch, events):
    _use_client(monkeypatch, _FakeClient(
        content='{"action_type": "show_hint", "reason": "ok", "urgency": "EXTREME"}'
    ))
    out = await ped.pedagogical_node(_state("confused"))
    assert out["strategy"]["urgency"] == "medium"
    assert out["strategy"]["fallback"] is False


async def test_content_context_is_used_in_prompt(monkeypatch, events):
    seen = {}

    class _CapturingClient(_FakeClient):
        async def ainvoke(self, messages):
            seen["human"] = messages[-1].content
            return _FakeResp('{"action_type": "no_action", "reason": "ok", "urgency": "low"}')

    _use_client(monkeypatch, _CapturingClient())
    await ped.pedagogical_node(_state("engaged", content_context={"topic": "subnetting", "difficulty": "hard"}))
    assert "subnetting" in seen["human"]
    assert "hard" in seen["human"]


async def test_prose_with_curly_braces_before_json_falls_back(monkeypatch, events):
    # LLM prefixes the JSON with prose that itself contains braces; the find/rfind
    # heuristic extracts from the first { to the last }, yielding invalid JSON → parse_error fallback.
    _use_client(monkeypatch, _FakeClient(
        content='Use {curly braces} in JSON: {"action_type": "show_hint", "reason": "ok", "urgency": "medium"}'
    ))
    out = await ped.pedagogical_node(_state("confused"))
    strat = out["strategy"]
    assert strat["fallback"] is True
    assert strat["fallback_reason"] == "parse_error"


# ── Escalation enforcement ──────────────────────────────────────────────────
#
# `rung` was accepted by `_build_human_prompt` and never written into the prompt, so the model was
# never told what had already been tried. Measured against gpt-4o-mini, the consequence was a
# learner still confused after a hint AND a breakdown receiving the same breakdown again, four
# times running.
#
# Putting the rung in the prompt was necessary and not sufficient: the model kept repeating. The
# no-repeat property is the entire reason the ladder exists, so it is enforced in code and the
# override is recorded rather than hidden.


class TestEscalationIsEnforced:
    def test_a_repeat_of_an_already_spent_rung_is_advanced(self):
        from app.agents.nodes.pedagogical import _enforce_escalation

        # Confused ladder: show_hint -> show_breakdown -> show_alternative.
        # At rung 2 a hint and a breakdown have already been delivered.
        strategy = {"action_type": "show_breakdown", "reason": "r", "urgency": "high"}
        out = _enforce_escalation(strategy, "confused", rung=2)

        assert out["action_type"] == "show_alternative"
        assert out["escalation_enforced"] is True
        # The model's own choice survives in the record: decision fidelity is measured, so an
        # overridden decision must not look like one the model made.
        assert out["model_action_type"] == "show_breakdown"

    def test_a_non_repeating_choice_is_left_alone(self):
        from app.agents.nodes.pedagogical import _enforce_escalation

        strategy = {"action_type": "suggest_break", "reason": "r", "urgency": "high"}
        out = _enforce_escalation(strategy, "confused", rung=2)

        assert out["action_type"] == "suggest_break"
        assert "escalation_enforced" not in out

    def test_rung_zero_never_overrides(self):
        """Nothing has been delivered yet, so nothing can be a repeat."""
        from app.agents.nodes.pedagogical import _enforce_escalation

        strategy = {"action_type": "show_hint", "reason": "r", "urgency": "low"}
        out = _enforce_escalation(strategy, "confused", rung=0)

        assert out == strategy

    def test_clamps_at_the_deepest_rung(self):
        """Past the last rung there is nothing deeper; repeating it is the least-bad option."""
        from app.agents.nodes.pedagogical import _enforce_escalation

        strategy = {"action_type": "show_video", "reason": "r", "urgency": "high"}
        out = _enforce_escalation(strategy, "confused", rung=5)

        assert out["action_type"] == "show_video"
        assert "escalation_enforced" not in out

    def test_boredom_advances_to_skip_ahead(self):
        from app.agents.nodes.pedagogical import _enforce_escalation

        strategy = {"action_type": "increase_difficulty", "reason": "r", "urgency": "low"}
        out = _enforce_escalation(strategy, "bored", rung=1)

        assert out["action_type"] == "skip_ahead"

    def test_an_unknown_state_is_left_alone(self):
        from app.agents.nodes.pedagogical import _enforce_escalation

        strategy = {"action_type": "show_hint", "reason": "r", "urgency": "low"}
        out = _enforce_escalation(strategy, "elated", rung=3)

        assert out == strategy


class TestTheRungReachesThePrompt:
    def test_prompt_states_how_many_interventions_were_delivered(self):
        from app.agents.nodes.pedagogical import _build_human_prompt

        prompt = _build_human_prompt("confused", 0.9, {"skill_level": "intermediate"}, {}, 2)

        assert "interventions_already_delivered: 2" in prompt

    def test_prompt_shows_the_ladder_for_this_state(self):
        """A count alone does not tell the model what the NEXT rung is."""
        from app.agents.nodes.pedagogical import _build_human_prompt

        prompt = _build_human_prompt("confused", 0.9, {"skill_level": "intermediate"}, {}, 1)

        assert "show_hint -> show_breakdown -> show_alternative" in prompt

    def test_the_ladder_shown_is_the_one_the_fallback_walks(self):
        """Restating it in prose would let the two drift, silently."""
        from app.agents import fallbacks
        from app.agents.nodes.pedagogical import _build_human_prompt

        for state in ("confused", "bored", "frustrated"):
            prompt = _build_human_prompt(state, 0.9, {}, {}, 1)
            assert " -> ".join(fallbacks.ladder_actions(state)) in prompt
