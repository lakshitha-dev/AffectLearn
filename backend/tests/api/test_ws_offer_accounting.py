"""What an offer costs, and when: only a card that reaches the learner spends anything.

The gate used to spend the cooldown, the session cap and a ladder rung the moment it passed --
before the strategist had chosen an action. A cycle that then produced nothing (the strategist's
`no_action`, text identical to earlier help, a card for a section the learner had left, a failed
send) still cost the learner a cooldown window, a sixth of the session's allowance, and a rung:
the ladder could climb, or reach `ladder_exhausted`, on help that was never shown.

These tests pin the socket-side half of the fix: `_deliver_adaptation` spends the carried
`offer_commit` after a successful send and in no other case.
"""

import pytest

import app.agents.nodes.learner_profiler as lp
import app.api.routes.ws as ws
from app.agents import edges
from app.agents.nodes.terminal import deliver_node
from app.services import redis_service

pytestmark = pytest.mark.asyncio

USER = "learner-offer"
PROFILE_KEY = f"profile:learner:{USER}"


@pytest.fixture(autouse=True)
def memory_redis(monkeypatch):
    store: dict = {PROFILE_KEY: {"cycle_count": 4}}

    async def get_json(key):
        value = store.get(key)
        return dict(value) if isinstance(value, dict) else value

    async def set_json(key, value, ttl_seconds=None):
        store[key] = value

    monkeypatch.setattr(redis_service, "get_json", get_json)
    monkeypatch.setattr(redis_service, "set_json", set_json)
    return store


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    async def fake_emit(event):
        return None

    async def no_ledger(*a, **k):
        return None

    monkeypatch.setattr(ws, "emit_research_event", fake_emit)
    monkeypatch.setattr(ws, "_record_assistance", no_ledger)


def _sender(monkeypatch, ok: bool = True) -> list:
    messages: list = []

    async def send_to(user_id, message):
        messages.append(message)
        return ok

    monkeypatch.setattr(ws.connection_manager, "send_to", send_to)
    return messages


def _offer(reason="ok", section="sec-A", state="bored"):
    return {"gate_reason": reason, "session_id": "s1", "section_id": section,
            "affect_state": state}


def _result(section="sec-A", action="show_hint", offer=None):
    return {
        "delivery_message": {
            "type": "adaptation", "adaptation_id": "a1", "action": action,
            "content": {"text": "hint", "variant": action}, "section_id": section,
        },
        "adaptation_content": {"metadata": {"action_type": action}},
        "offer_commit": offer if offer is not None else _offer(section=section),
    }


def _profile(store) -> dict:
    return store[PROFILE_KEY]


async def _on_section(section: str) -> None:
    await ws._handle_ui_event(
        {"type": "ui_event", "ts": 1, "data": {"event": "section_entered", "section_id": section}},
        USER,
    )


def _spent_nothing(profile: dict) -> None:
    assert "last_adaptation_ms" not in profile
    assert not profile.get("eligible_this_session")
    assert not profile.get("ladder_rungs")


async def test_a_delivered_card_spends_cooldown_cap_and_rung(memory_redis, monkeypatch):
    sent = _sender(monkeypatch)
    await _on_section("sec-A")

    await ws._deliver_adaptation(_result(), USER, "s1", 5)

    assert len(sent) == 1
    prof = _profile(memory_redis)
    assert prof["last_adaptation_session"] == "s1"
    assert isinstance(prof["last_adaptation_ms"], int)
    assert prof["eligible_this_session"] == 1
    assert prof["ladder_rungs"] == {"sec-A|bored": 1}


async def test_a_stale_card_spends_nothing(memory_redis, monkeypatch):
    sent = _sender(monkeypatch)
    await _on_section("sec-B")                     # the learner has moved on

    await ws._deliver_adaptation(_result(section="sec-A"), USER, "s1", 5)

    assert sent == []
    _spent_nothing(_profile(memory_redis))


async def test_a_failed_send_spends_nothing(memory_redis, monkeypatch):
    _sender(monkeypatch, ok=False)
    await _on_section("sec-A")

    await ws._deliver_adaptation(_result(), USER, "s1", 5)

    _spent_nothing(_profile(memory_redis))


async def test_no_action_spends_nothing(memory_redis, monkeypatch):
    """The strategist chose `no_action`: the deliver node builds no message, so nothing is sent."""
    sent = _sender(monkeypatch)
    await _on_section("sec-A")
    built = await deliver_node({
        "adaptation_content": {"text": "", "variant": "no_action",
                               "metadata": {"action_type": "no_action"}},
        "content_context": {"section_id": "sec-A"},
    })
    assert built == {}

    await ws._deliver_adaptation({**built, "offer_commit": _offer()}, USER, "s1", 5)

    assert sent == []
    _spent_nothing(_profile(memory_redis))


async def test_a_suppressed_duplicate_spends_nothing(memory_redis, monkeypatch):
    """The adapter dropped text identical to earlier help, so the cycle carries no content."""
    sent = _sender(monkeypatch)
    await _on_section("sec-A")
    built = await deliver_node({"adaptation_content": None,
                                "content_context": {"section_id": "sec-A"}})
    assert built == {}

    await ws._deliver_adaptation({**built, "offer_commit": _offer()}, USER, "s1", 5)

    assert sent == []
    _spent_nothing(_profile(memory_redis))


async def test_a_delivered_learner_request_advances_only_the_ladder(memory_redis, monkeypatch):
    _sender(monkeypatch)
    await _on_section("sec-A")

    await ws._deliver_adaptation(
        _result(offer=_offer(reason="learner_request", state="confused")), USER, "s1", 5
    )

    prof = _profile(memory_redis)
    assert prof["ladder_rungs"] == {"sec-A|confused": 1}
    assert "last_adaptation_ms" not in prof
    assert not prof.get("eligible_this_session")


async def test_the_cap_counts_delivered_cards_only(memory_redis, monkeypatch):
    """Six delivered cards reach the cap; dropped ones in between do not count toward it."""
    _sender(monkeypatch)
    await _on_section("sec-A")
    for _ in range(edges.ADAPT_MAX_PER_SESSION):
        await ws._deliver_adaptation(_result(), USER, "s1", 5)
        await ws._deliver_adaptation(_result(section="sec-Z"), USER, "s1", 5)   # stale: dropped

    prof = _profile(memory_redis)
    assert prof["eligible_this_session"] == edges.ADAPT_MAX_PER_SESSION
    assert edges._session_cap_reached(prof, "s1") is True


async def test_commit_uses_the_same_clock_as_the_gate(memory_redis, monkeypatch):
    _sender(monkeypatch)
    monkeypatch.setattr(lp, "_clock_ms", lambda: 123_456_789)
    await _on_section("sec-A")

    await ws._deliver_adaptation(_result(), USER, "s1", 5)

    assert _profile(memory_redis)["last_adaptation_ms"] == 123_456_789
