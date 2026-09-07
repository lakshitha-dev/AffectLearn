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


async def test_increase_difficulty_generates_a_challenge_rather_than_selecting(monkeypatch, events):
    """It used to emit a `challenge_exercise` selection descriptor and deliver NOTHING.

    The catalog that descriptor pointed at never existed -- no table, no resolver, no difficulty
    column on any content model -- so the client rendered null and a bored learner saw an empty
    box. Since this is the only response to boredom that raises challenge, and flow theory puts
    boredom at challenge BELOW skill, leaving it unimplemented left the boredom branch with
    nothing but pagination. It is now generative, written against the section body the adapter
    is already given.
    """
    _boom_client(monkeypatch)   # LLM unavailable -> pre-written challenge copy
    out = await ca.content_adapter_node(_state("increase_difficulty", affect="bored"))
    content = out["adaptation_content"]

    assert "select" not in content["metadata"], "no longer a selection descriptor"
    assert content["metadata"]["fallback"] is True, "LLM was down, so this is the written copy"
    assert content["text"].strip(), "a bored learner must actually receive something"
    assert "?" in content["text"], "the challenge has to ask something, not announce something"
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


async def test_assessment_blocks_never_reach_the_prompt(monkeypatch, events):
    """Neither the ANSWER nor the QUESTION may reach the model.

    Regression for a real production leak: the "Constrained Decoding and Grammars" section asks
    "why can a model ... never emit invalid JSON? What might it give up in exchange?" and the
    delivered hint answered both halves ("only move along valid paths ... sacrifice some speed
    or flexibility"). Excluding only the answer was not enough — showing a model a question is
    enough to leak the answer.
    """
    from app.services import content_context_service as ccs
    from app.models.course import BlockType

    class _Block:
        def __init__(self, block_type, content, sort_order=0):
            self.block_type = block_type
            self.content = content
            self.sort_order = sort_order

    rendered = ccs._render_body([
        _Block(BlockType.text, {"text": "Constrained decoding masks invalid tokens."}, 0),
        _Block(BlockType.exercise, {
            "prompt": "Why can a model never emit invalid JSON? What might it give up?",
            "answer": "SECRET_ANSWER",
        }, 1),
        _Block(BlockType.quiz, {
            "question": "Which token set is admissible at position t?",
            "options": [["A_t", True]],
        }, 2),
    ])

    assert "Constrained decoding masks invalid tokens." in rendered
    assert "SECRET_ANSWER" not in rendered
    assert "What might it give up" not in rendered, "exercise QUESTION leaked"
    assert "admissible at position t" not in rendered, "quiz QUESTION leaked"
    assert "asked a question here" in rendered, "should still signal an assessment exists"


async def test_system_prompt_forbids_answering_questions():
    """Second layer: prose questions no block filter can catch."""
    assert "NEVER answer" in ca._SYSTEM_PROMPT


# ── markdown sanitising (2026-08-29) ──────────────────────────────────────────
#
# Observed in production: a delivered breakdown read
#   "**Class and Main Method**: The program starts with a class named `Report`"
# `AdaptiveHintCallout` renders the reply as plain text, so markdown reaches the learner as
# literal asterisks and backticks. The system prompt forbids markdown and that IS enough for
# `show_hint` — but `show_breakdown` reverts to bold-labelled lists regardless of instruction.


def test_strips_bold_and_backticks():
    out = ca._strip_markdown("**Class**: use `equals()` not `==`")
    assert "**" not in out and "`" not in out
    assert "Class: use equals() not ==" in out


def test_preserves_numbering_for_the_ordered_list_parser():
    """The breakdown variant parses `1.` / `2.` into an <ol>; stripping them would break it."""
    out = ca._strip_markdown("1. First step\n2. Second step")
    assert out.startswith("1. First step")
    assert "2. Second step" in out


def test_strips_bullet_and_heading_markers():
    out = ca._strip_markdown("## Heading\n- bullet one\n* bullet two")
    assert not out.startswith("#")
    assert "bullet one" in out and "- bullet" not in out and "* bullet" not in out


def test_system_prompt_demands_plain_text_and_brevity():
    assert "PLAIN TEXT ONLY" in ca._SYSTEM_PROMPT
    assert "80 words" in ca._SYSTEM_PROMPT


async def test_generated_text_has_markdown_removed(monkeypatch, events):
    """The sanitiser must sit on the real generation path, not just exist as a helper."""
    _use_client(monkeypatch, _FakeClient(content="**Bold** and `code` here"))
    out = await ca.content_adapter_node(_state("show_hint"))
    text = out["adaptation_content"]["text"]
    assert "**" not in text and "`" not in text
    assert "Bold and code here" in text


def test_max_tokens_headroom_against_truncation():
    """A breakdown was cut off mid-sentence at 256 tokens (181 words ~ 280 tokens)."""
    from app.core.config import settings as _s
    assert _s.VLLM_MAX_TOKENS >= 400


# ── Authored content variants (FR19 / FR21) ─────────────────────────────────
#
# `content_blocks.variant_key` existed from migration 005 and nothing ever wrote anything but
# "original" into it, so `show_alternative` and `increase_difficulty` always fell through to
# generated prose and `skip_ahead` pointed at a catalogue that did not exist. With a catalogue
# behind them, a designer's own alternative wording for THIS material outranks an LLM paraphrase
# of the section it stands in for.


class _Block:
    """Minimal stand-in for a `ContentBlock` row."""

    def __init__(self, text):
        self.content = {"text": text}


def _with_variant(monkeypatch, text, *, expect_key=None):
    """Patch the variant lookup, optionally asserting which key was requested."""
    seen = {}

    async def _find_variant(db, *, section_id, variant_key):
        seen["section_id"] = section_id
        seen["variant_key"] = variant_key
        if expect_key is not None and variant_key != expect_key:
            return None
        return _Block(text) if text is not None else None

    from app.services import course_service

    monkeypatch.setattr(course_service, "find_variant", _find_variant)
    return seen


def _variant_state(action, **kw):
    state = _state(action, **kw)
    state["content_context"] = {"section_id": "sec-1", "section_title": "T"}
    state["db"] = object()  # only ever handed to the patched lookup
    return state


async def test_authored_alternative_is_served_instead_of_calling_the_llm(monkeypatch, events):
    _boom_client(monkeypatch)  # the LLM must not be reached when a variant exists
    seen = _with_variant(monkeypatch, "Here is the same idea from another angle.")

    out = await ca.content_adapter_node(_variant_state("show_alternative"))

    content = out["adaptation_content"]
    assert content["text"] == "Here is the same idea from another angle."
    assert content["metadata"]["authored_variant"] is True
    assert content["metadata"]["generated"] is False
    assert content["metadata"]["fallback"] is False
    assert seen["variant_key"] == "alternative"


async def test_increase_difficulty_selects_the_harder_variant(monkeypatch, events):
    _boom_client(monkeypatch)
    seen = _with_variant(monkeypatch, "Now try this harder version.")

    out = await ca.content_adapter_node(_variant_state("increase_difficulty"))

    assert out["adaptation_content"]["text"] == "Now try this harder version."
    assert seen["variant_key"] == "harder"


async def test_breakdown_and_simplify_select_the_simpler_variant(monkeypatch, events):
    _boom_client(monkeypatch)
    seen = _with_variant(monkeypatch, "Step by step, in plainer words.")

    await ca.content_adapter_node(_variant_state("show_breakdown"))
    assert seen["variant_key"] == "simpler"

    await ca.content_adapter_node(_variant_state("simplify"))
    assert seen["variant_key"] == "simpler"


async def test_skip_ahead_descriptor_points_at_real_content(monkeypatch, events):
    """`skip_ahead` is selective: its descriptor used to name a catalogue that did not exist."""
    seen = _with_variant(monkeypatch, "The challenge version.")

    out = await ca.content_adapter_node(_variant_state("skip_ahead"))

    md = out["adaptation_content"]["metadata"]
    assert md["select"] == "authored_variant"
    assert md["authored_variant"] is True
    assert out["adaptation_content"]["text"] == "The challenge version."
    assert seen["variant_key"] == "harder"


async def test_falls_back_to_generation_when_no_variant_is_authored(monkeypatch, events):
    """Having no authored variant is the ordinary case and must not cost an intervention."""
    _use_client(monkeypatch, _FakeClient(content="Generated instead."))
    _with_variant(monkeypatch, None)

    out = await ca.content_adapter_node(_variant_state("show_alternative"))

    content = out["adaptation_content"]
    assert content["text"] == "Generated instead."
    assert content["metadata"].get("authored_variant") is not True


async def test_hints_never_select_a_variant(monkeypatch, events):
    """A hint addresses the learner's difficulty; it is not a substitute rendering of content."""
    _use_client(monkeypatch, _FakeClient(content="A hint."))

    called = {"n": 0}

    async def _find_variant(db, *, section_id, variant_key):
        called["n"] += 1
        return _Block("should not be used")

    from app.services import course_service

    monkeypatch.setattr(course_service, "find_variant", _find_variant)

    out = await ca.content_adapter_node(_variant_state("show_hint"))

    assert called["n"] == 0
    assert out["adaptation_content"]["text"] == "A hint."


async def test_a_lookup_failure_degrades_to_generation(monkeypatch, events):
    """NFR22: the node never raises, and a broken lookup must not lose the intervention."""
    _use_client(monkeypatch, _FakeClient(content="Generated after failure."))

    async def _boom(db, *, section_id, variant_key):
        raise RuntimeError("database went away")

    from app.services import course_service

    monkeypatch.setattr(course_service, "find_variant", _boom)

    out = await ca.content_adapter_node(_variant_state("show_alternative"))

    assert out["adaptation_content"]["text"] == "Generated after failure."


async def test_no_section_context_means_no_variant_lookup(monkeypatch, events):
    _use_client(monkeypatch, _FakeClient(content="Generated."))
    called = {"n": 0}

    async def _find_variant(db, *, section_id, variant_key):
        called["n"] += 1
        return None

    from app.services import course_service

    monkeypatch.setattr(course_service, "find_variant", _find_variant)

    state = _state("show_alternative")  # no content_context, no db
    out = await ca.content_adapter_node(state)

    assert called["n"] == 0
    assert out["adaptation_content"]["text"] == "Generated."


async def test_research_event_records_whether_a_human_wrote_it(monkeypatch, events):
    _boom_client(monkeypatch)
    _with_variant(monkeypatch, "Designer's own wording.")

    await ca.content_adapter_node(_variant_state("show_alternative"))

    evt = [e for e in events if e["event_type"] == "adaptation_triggered"][-1]
    assert evt["payload"]["authored_variant"] is True
