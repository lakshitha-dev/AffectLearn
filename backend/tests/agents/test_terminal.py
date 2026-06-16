"""Unit tests for the terminal nodes (Story 5.3 — `deliver_node` builds the wire payload).

`deliver_node` is socket-free: it reads `AgentState.adaptation_content` and returns a
`{"delivery_message": {...}}` partial update (or `{}` when nothing should be delivered).
It must never raise on malformed content (NFR22).
"""

import pytest

from app.agents.nodes.terminal import deliver_node, log_only_node

pytestmark = pytest.mark.asyncio


def _generative_content():
    return {
        "text": "Here's a gentler way to think about it.",
        "variant": "show_hint",
        "metadata": {"action_type": "show_hint", "generated": True, "fallback": False},
    }


def _selective_content():
    return {
        "text": "You've got a good handle on this — let's move ahead.",
        "variant": "skip_ahead",
        "metadata": {"action_type": "skip_ahead", "generated": False, "fallback": False,
                     "select": "next_section"},
    }


async def test_deliver_builds_payload_from_generative_content():
    out = await deliver_node({"adaptation_content": _generative_content()})
    msg = out["delivery_message"]
    assert msg["type"] == "adaptation"
    assert msg["action"] == "show_hint"
    assert msg["content"] == {"text": "Here's a gentler way to think about it.",
                              "variant": "show_hint"}
    assert isinstance(msg["ts"], int) and msg["ts"] > 0


async def test_deliver_builds_payload_from_selective_content():
    out = await deliver_node({"adaptation_content": _selective_content()})
    msg = out["delivery_message"]
    assert msg["action"] == "skip_ahead"
    assert msg["content"]["variant"] == "skip_ahead"


async def test_deliver_falls_back_to_variant_when_action_type_missing():
    content = {"text": "hi", "variant": "show_breakdown", "metadata": {}}
    out = await deliver_node({"adaptation_content": content})
    assert out["delivery_message"]["action"] == "show_breakdown"


async def test_deliver_no_action_returns_empty():
    content = {"text": "", "variant": "no_action", "metadata": {"action_type": "no_action"}}
    out = await deliver_node({"adaptation_content": content})
    assert out == {}


async def test_deliver_absent_content_returns_empty():
    assert await deliver_node({}) == {}


async def test_deliver_empty_content_returns_empty():
    assert await deliver_node({"adaptation_content": {}}) == {}
    assert await deliver_node({"adaptation_content": None}) == {}


async def test_deliver_malformed_content_does_not_raise():
    # Non-dict adaptation_content / missing metadata / junk -> no delivery, no raise.
    assert await deliver_node({"adaptation_content": "junk"}) == {}
    assert await deliver_node({"adaptation_content": 123}) == {}
    assert await deliver_node({"adaptation_content": ["a"]}) == {}
    # dict with no variant/action_type at all -> nothing to deliver.
    assert await deliver_node({"adaptation_content": {"text": "orphan"}}) == {}
    # metadata not a dict -> fall back to variant, still delivers.
    out = await deliver_node({"adaptation_content": {"variant": "simplify", "metadata": "bad"}})
    assert out["delivery_message"]["action"] == "simplify"


async def test_log_only_unchanged():
    assert await log_only_node({"affect_state": "engaged"}) == {}
