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
