"""The Pedagogical agent's Video sub-agent: delegation, the parallel fan-out, and delivery."""

from __future__ import annotations

import json

import pytest

import app.agents.nodes.content_adapter as ca
import app.agents.nodes.pedagogical as ped
import app.agents.nodes.video_resource as vr
from app.agents import fallbacks
from app.agents.graph import build_graph
from app.agents.nodes.terminal import _build_delivery_message
from app.agents.state import AFFECT_SOURCE_LEARNER_REQUEST, make_initial_state
from app.services import video_resource_agent

pytestmark = pytest.mark.asyncio

EMBED = {"kind": "embed", "url": "https://www.youtube.com/watch?v=BBB", "video_id": "BBB",
         "title": "Why range stops early", "channel": "Y", "duration_s": 300,
         "reason": "Shows it.", "query": "q", "concept": "c", "source": "api"}


# ── the vocabulary and the delegation brief ──────────────────────────────────────────


def test_show_video_is_the_last_confusion_rung():
    assert "show_video" in fallbacks.ACTION_TYPES
    assert fallbacks.ladder_actions("confused")[-1] == "show_video"
    assert "show_video" in fallbacks.GENERATIVE_ACTIONS


def test_the_strategist_brief_is_parsed_for_show_video_only():
    text = json.dumps({"action_type": "show_video", "reason": "r", "urgency": "high",
                       "video_brief": {"concept": "range end value",
                                       "query": "python range stop value explained"}})
    assert ped._parse_strategy(text)["video_brief"] == {
        "concept": "range end value", "query": "python range stop value explained"
    }
    hint = json.dumps({"action_type": "show_hint", "reason": "r", "urgency": "low",
                       "video_brief": {"concept": "x", "query": "y"}})
    assert "video_brief" not in ped._parse_strategy(hint)


def test_an_incomplete_brief_is_dropped_not_half_used():
    text = json.dumps({"action_type": "show_video", "reason": "r", "urgency": "high",
                       "video_brief": {"concept": "range"}})
    assert "video_brief" not in ped._parse_strategy(text)


# ── the node ─────────────────────────────────────────────────────────────────────────


def _state(action="show_video", brief=None):
    state = make_initial_state(learner_id="l1", session_id="s1", cycle_number=3,
                               phase="phase_b", group="adaptive",
                               content_context={"section_id": "sec", "topic": "Loops"})
    state["strategy"] = {"action_type": action, **({"video_brief": brief} if brief else {})}
    return state


@pytest.fixture
def events(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event):
        captured.append(event)

    monkeypatch.setattr(vr, "emit_research_event", fake_emit)
    return captured


async def test_other_actions_are_a_no_op(monkeypatch, events):
    async def never(*a, **k):
        raise AssertionError("the sub-agent must not run for a hint")

    monkeypatch.setattr(video_resource_agent, "find_video", never)
    assert await vr.video_resource_node(_state("show_hint")) == {}
    assert events == []


async def test_the_brief_is_delegated_and_the_video_reported(monkeypatch, events):
    seen = {}

    async def fake_find(context, last_hint_text=None, brief=None, timeout_s=None):
        seen.update(brief=brief, timeout_s=timeout_s)
        return EMBED

    monkeypatch.setattr(video_resource_agent, "find_video", fake_find)
    brief = {"concept": "range end value", "query": "python range stop explained"}
    out = await vr.video_resource_node(_state(brief=brief))

    assert seen["brief"] == brief
    assert seen["timeout_s"] == vr.SUBAGENT_TIMEOUT_S
    assert out["video_resource"]["video_id"] == "BBB"
    # Internals stay server-side.
    assert "source" not in out["video_resource"] and "query" not in out["video_resource"]
    assert events[0]["event_type"] == "video_resource_selected"
    assert events[0]["payload"]["brief"] == brief


async def test_a_slow_search_hands_the_client_the_brief(monkeypatch, events):
    async def slow(context, last_hint_text=None, brief=None, timeout_s=None):
        return {"kind": "link", "url": "u", "source": "fallback"}

    monkeypatch.setattr(video_resource_agent, "find_video", slow)
    brief = {"concept": "range end value", "query": "python range stop explained"}
    out = await vr.video_resource_node(_state(brief=brief))
    assert out["video_resource"] == {"pending": True, "concept": "range end value",
                                     "query": "python range stop explained"}


# ── delivery ─────────────────────────────────────────────────────────────────────────


def test_only_a_show_video_card_carries_the_video():
    content = {"text": "Watch this.", "variant": "show_video",
               "metadata": {"action_type": "show_video"}}
    msg = _build_delivery_message(content, {"kind": "embed", "video_id": "BBB", "url": "u"})
    assert msg["action"] == "show_video"
    assert msg["video"]["video_id"] == "BBB"

    hint = {"text": "Hint.", "variant": "show_hint", "metadata": {"action_type": "show_hint"}}
    assert "video" not in _build_delivery_message(hint, {"kind": "embed", "video_id": "BBB"})


# ── the whole graph: fan-out to adapter and sub-agent, joined once at deliver ────────


class _Reply:
    def __init__(self, content):
        self.content = content


class _Client:
    def __init__(self, content):
        self._content = content

    async def ainvoke(self, messages):
        return _Reply(self._content)


async def test_the_graph_delegates_in_parallel_and_delivers_once(monkeypatch, events):
    strategy_json = json.dumps({
        "action_type": "show_video", "reason": "text has not landed", "urgency": "high",
        "video_brief": {"concept": "range end value", "query": "python range stop explained"},
    })
    monkeypatch.setattr(ped, "get_chat_client", lambda: _Client(strategy_json))
    monkeypatch.setattr(ca, "get_chat_client",
                        lambda: _Client("Here is a short video on where range stops."))

    async def quiet(event):
        pass

    monkeypatch.setattr(ped, "emit_research_event", quiet)
    monkeypatch.setattr(ca, "emit_research_event", quiet)

    delegated = {}

    async def fake_find(context, last_hint_text=None, brief=None, timeout_s=None):
        delegated["brief"] = brief
        return EMBED

    monkeypatch.setattr(video_resource_agent, "find_video", fake_find)

    state = make_initial_state(learner_id="l-graph", session_id="s-graph", cycle_number=2,
                               phase="phase_b", group="adaptive",
                               content_context={"section_id": "sec", "topic": "Loops"})
    state["affect_state"] = "confused"
    state["affect_confidence"] = 1.0
    state["affect_source"] = AFFECT_SOURCE_LEARNER_REQUEST

    result = await build_graph().compile().ainvoke(state)

    assert delegated["brief"]["concept"] == "range end value"
    message = result["delivery_message"]
    assert message["action"] == "show_video"
    assert message["content"]["text"] == "Here is a short video on where range stops."
    assert message["video"]["video_id"] == "BBB"
