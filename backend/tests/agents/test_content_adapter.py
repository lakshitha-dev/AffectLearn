"""Tests for the Content Adapter node (Story 5.2 AC2/AC3/AC4/AC5).

vLLM is always mocked (no GPU): `get_chat_client` is monkeypatched to a fake client whose
`ainvoke` returns canned content, sleeps past the timeout, or raises. Selective / no_action
paths assert the LLM is NEVER reached.
"""

import asyncio

import pytest

import app.agents.llm as llm_mod
import app.agents.nodes.content_adapter as ca
from app.agents.state import make_initial_state
from app.core.config import settings

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def reset_llm_singleton():
    """Reset the vLLM client singleton before/after each test (mirrors test_pedagogical)."""
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

    monkeypatch.setattr(ca, "emit_research_event", fake_emit)
    return captured


def _use_client(monkeypatch, client):
    monkeypatch.setattr(ca, "get_chat_client", lambda: client)


def _boom_client(monkeypatch):
    def _boom():
        raise AssertionError("LLM must not be called on this path")

    monkeypatch.setattr(ca, "get_chat_client", _boom)


def _state(action="show_hint", affect="confused", **kw):
    state = make_initial_state(
        learner_id="u1", session_id="s1", cycle_number=2,
        phase="phase_b", group="adaptive", **kw,
    )
    if affect is not None:
        state["affect_state"] = affect
        state["affect_confidence"] = 0.82
        state["detection_mode"] = "facial_only"
    state["learner_profile"] = {"skill_level": "intermediate"}
    if action is not None:
        state["strategy"] = {"action_type": action, "reason": "x", "urgency": "medium",
                             "fallback": False}
    return state


# ── Generative path ─────────────────────────────────────────────────────────


async def test_generative_success_uses_llm_content(monkeypatch, events):
    _use_client(monkeypatch, _FakeClient(content="Try thinking of it like a recipe."))
    out = await ca.content_adapter_node(_state("show_hint"))
    content = out["adaptation_content"]
    assert content["text"] == "Try thinking of it like a recipe."
    assert content["variant"] == "show_hint"
    assert content["metadata"]["generated"] is True
    assert content["metadata"]["fallback"] is False
    assert content["metadata"]["affect_state"] == "confused"
    assert events[0]["event_type"] == "adaptation_triggered"
    assert events[0]["payload"]["generated"] is True
    assert events[0]["payload"]["fallback"] is False


async def test_generative_strips_whitespace_and_normalises_blocks(monkeypatch, events):
    _use_client(monkeypatch, _FakeClient(content=[{"text": "Step one. "}, {"text": "Step two."}]))
    out = await ca.content_adapter_node(_state("show_breakdown"))
    assert out["adaptation_content"]["text"] == "Step one. Step two."
    assert out["adaptation_content"]["metadata"]["generated"] is True


async def test_timeout_falls_back(monkeypatch, events):
    monkeypatch.setattr(settings, "VLLM_TIMEOUT_SECONDS", 0.05)
    _use_client(monkeypatch, _FakeClient(content="too slow", delay=0.5))
    out = await ca.content_adapter_node(_state("show_alternative"))
    md = out["adaptation_content"]["metadata"]
    assert md["fallback"] is True
    assert md["fallback_reason"] == "timeout"
    assert md["generated"] is False
    assert out["adaptation_content"]["text"]  # pre-written copy is non-empty
    assert out["adaptation_content"]["variant"] == "show_alternative"
    assert events[0]["payload"]["fallback_reason"] == "timeout"


async def test_vllm_error_falls_back(monkeypatch, events):
    _use_client(monkeypatch, _FakeClient(exc=RuntimeError("connection refused")))
    out = await ca.content_adapter_node(_state("show_encouragement"))
    md = out["adaptation_content"]["metadata"]
    assert md["fallback"] is True
    assert md["fallback_reason"] == "vllm_error"
    assert out["adaptation_content"]["text"]


async def test_empty_response_falls_back_parse_error(monkeypatch, events):
    _use_client(monkeypatch, _FakeClient(content="   \n  "))
    out = await ca.content_adapter_node(_state("suggest_break"))
    md = out["adaptation_content"]["metadata"]
    assert md["fallback"] is True
    assert md["fallback_reason"] == "parse_error"
    assert out["adaptation_content"]["text"]
    assert events[0]["payload"]["fallback_reason"] == "parse_error"


async def test_simplify_is_generative(monkeypatch, events):
    _use_client(monkeypatch, _FakeClient(content="Let's take it gently."))
    out = await ca.content_adapter_node(_state("simplify"))
    assert out["adaptation_content"]["metadata"]["generated"] is True
    assert out["adaptation_content"]["variant"] == "simplify"


# ── Selective path (no LLM) ───────────────────────────────────────────────────


async def test_skip_ahead_selects_without_calling_llm(monkeypatch, events):
    _boom_client(monkeypatch)
    out = await ca.content_adapter_node(_state("skip_ahead", affect="bored"))
    content = out["adaptation_content"]
    assert content["variant"] == "skip_ahead"
    assert content["metadata"]["select"] == "next_section"
    assert content["metadata"]["generated"] is False
    assert content["metadata"]["fallback"] is False
    assert content["metadata"]["affect_state"] == "bored"
    assert events[0]["event_type"] == "adaptation_triggered"
    assert events[0]["payload"]["variant"] == "skip_ahead"
    assert events[0]["payload"]["generated"] is False


async def test_increase_difficulty_selects_without_calling_llm(monkeypatch, events):
    _boom_client(monkeypatch)
    out = await ca.content_adapter_node(_state("increase_difficulty", affect="bored"))
    content = out["adaptation_content"]
    assert content["metadata"]["select"] == "challenge_exercise"
    assert content["metadata"]["fallback"] is False
    assert len(events) == 1


# ── no_action / missing strategy ──────────────────────────────────────────────


async def test_no_action_returns_empty_and_emits_no_event(monkeypatch, events):
    _boom_client(monkeypatch)
    out = await ca.content_adapter_node(_state("no_action", affect="engaged"))
    assert out == {}
    assert events == []


async def test_missing_strategy_returns_empty(monkeypatch, events):
    _boom_client(monkeypatch)
    out = await ca.content_adapter_node(_state(action=None, affect="engaged"))
    assert out == {}
    assert events == []


async def test_event_payload_shape_on_generative(monkeypatch, events):
    _use_client(monkeypatch, _FakeClient(content="A warm hint."))
    await ca.content_adapter_node(_state("show_hint"))
    payload = events[0]["payload"]
    assert set(payload) >= {
        "action_type", "variant", "affect_state", "detection_mode", "generated",
        "fallback", "fallback_reason",
    }
    assert payload["action_type"] == "show_hint"
    assert payload["affect_state"] == "confused"
    assert payload["detection_mode"] == "facial_only"
    # fallback_reason is None (not applicable) on the LLM success path
    assert payload["fallback_reason"] is None
    ev = events[0]
    assert ev["learner_id"] == "u1"
    assert ev["session_id"] == "s1"
    assert ev["cycle_number"] == 2
    assert isinstance(ev["timestamp"], int)


async def test_unknown_action_type_returns_empty_and_emits_no_event(monkeypatch, events):
    """Out-of-vocabulary action_type (not no_action, not generative, not selective)
    should return {} without calling the LLM and without emitting any event."""
    _boom_client(monkeypatch)
    out = await ca.content_adapter_node(_state("teleport_learner", affect="confused"))
    assert out == {}
    assert events == []


# ── Prompt grounding (2026-08-29) ─────────────────────────────────────────────
#
# `content_context` was never populated by either `ws.py` call site, so every prompt read
# `content_topic: unknown` and the model could only produce generic study advice —
# indistinguishable from the rule-based fallback sitting next to it. These lock in that the
# section's real material reaches the prompt.

_SECTION_BODY = (
    "Structured output constrains the model to emit JSON conforming to a schema you supply, "
    "so your code can treat it like any other well-behaved API."
)


def _grounded_state(**kw):
    return _state(
        content_context={
            "topic": "Structured Output",
            "lesson": "Giving Agents Capabilities",
            "body": _SECTION_BODY,
            "difficulty": "unknown",
        },
        **kw,
    )


async def test_prompt_includes_section_body_and_titles(monkeypatch, events):
    """The section text, topic and lesson all reach the human prompt."""
    client = _FakeClient(content="Think about what the schema guarantees your parser.")
    _use_client(monkeypatch, client)
    captured = {}

    async def _capture(messages):
        captured["human"] = messages[-1].content
        return _FakeResp("Think about what the schema guarantees your parser.")

    client.ainvoke = _capture

    await ca.content_adapter_node(_grounded_state())

    human = captured["human"]
    assert _SECTION_BODY in human, "section body must reach the model"
    assert "Structured Output" in human
    assert "Giving Agents Capabilities" in human
    assert "content_topic: unknown" not in human


async def test_prompt_without_context_omits_body_block(monkeypatch, events):
    """No section id -> no body block, and the prompt still builds (no crash, no empty fence)."""
    client = _FakeClient(content="ok")
    _use_client(monkeypatch, client)
    captured = {}

    async def _capture(messages):
        captured["human"] = messages[-1].content
        return _FakeResp("ok")

    client.ainvoke = _capture

    await ca.content_adapter_node(_state())  # no content_context

    human = captured["human"]
    assert "currently reading this section" not in human
    assert "content_topic: unknown" in human


async def test_quiz_and_exercise_answers_never_reach_the_prompt(monkeypatch, events):
    """`show_hint` must not be handed the answer key — `_block_text` excludes answers."""
    from app.services import content_context_service as ccs
    from app.models.course import BlockType

    class _Block:
        def __init__(self, block_type, content, sort_order=0):
            self.block_type = block_type
            self.content = content
            self.sort_order = sort_order

    rendered = ccs._render_body([
        _Block(BlockType.exercise, {"prompt": "Write a schema.", "answer": "SECRET_ANSWER"}),
        _Block(BlockType.quiz, {"question": "Which is valid?", "options": [["a", True]]}),
    ])
    assert "Write a schema." in rendered
    assert "SECRET_ANSWER" not in rendered
