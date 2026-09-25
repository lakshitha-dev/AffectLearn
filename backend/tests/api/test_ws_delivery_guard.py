"""The WebSocket side of the delivery guard: screen events in, stale cards refused, answers applied."""

import pytest

import app.api.routes.ws as ws
from app.services import redis_service

pytestmark = pytest.mark.asyncio

USER = "learner-guard"


@pytest.fixture(autouse=True)
def memory_redis(monkeypatch):
    store: dict = {}

    async def get_json(key):
        return store.get(key)

    async def set_json(key, value, ttl_seconds=None):
        store[key] = value

    monkeypatch.setattr(redis_service, "get_json", get_json)
    monkeypatch.setattr(redis_service, "set_json", set_json)
    return store


@pytest.fixture
def sent(monkeypatch):
    messages: list = []

    async def send_to(user_id, message):
        messages.append(message)
        return True

    monkeypatch.setattr(ws.connection_manager, "send_to", send_to)
    return messages


@pytest.fixture
def events(monkeypatch):
    captured: list = []

    async def fake_emit(event):
        captured.append(event)

    monkeypatch.setattr(ws, "emit_research_event", fake_emit)

    async def no_ledger(*a, **k):
        return None

    monkeypatch.setattr(ws, "_record_assistance", no_ledger)
    return captured


def _ui(store):
    return store.get(f"ui:learner:{USER}") or {}


def _event(event, **data):
    return {"type": "ui_event", "ts": 1, "data": {"event": event, **data}}


def _result(section_id, action="show_hint"):
    return {
        "delivery_message": {
            "type": "adaptation",
            "adaptation_id": "a1",
            "action": action,
            "content": {"text": "hint", "variant": action},
            "section_id": section_id,
        },
        "adaptation_content": {"metadata": {"action_type": action}},
    }


async def test_section_entered_is_recorded(memory_redis):
    await ws._handle_ui_event(_event("section_entered", section_id="sec-A"), USER)
    ui = _ui(memory_redis)
    assert ui["section_id"] == "sec-A"
    assert ui["entered_ms"] > 0


async def test_unknown_ui_events_are_dropped(memory_redis):
    await ws._handle_ui_event(_event("teleport"), USER)
    assert _ui(memory_redis) == {}


async def test_visibility_and_quiz_activity_are_recorded(memory_redis):
    await ws._handle_ui_event(_event("visibility", visible=False), USER)
    await ws._handle_ui_event(_event("quiz_activity"), USER)
    ui = _ui(memory_redis)
    assert ui["page_hidden"] is True
    assert ui["quiz_until_ms"] > 0


async def test_a_card_for_a_section_the_learner_left_is_not_sent(memory_redis, sent, events):
    await ws._handle_ui_event(_event("section_entered", section_id="sec-B"), USER)
    await ws._deliver_adaptation(_result("sec-A"), USER, "s1", 5)
    assert sent == []
    dropped = [e for e in events if e["event_type"] == "adaptation_dropped"]
    assert dropped and dropped[0]["payload"]["reason"] == "stale_section"


async def test_a_delivered_card_is_marked_open(memory_redis, sent, events):
    await ws._handle_ui_event(_event("section_entered", section_id="sec-A"), USER)
    await ws._deliver_adaptation(_result("sec-A", action="show_video"), USER, "s1", 5)
    assert len(sent) == 1
    assert sent[0]["section_id"] == "sec-A"
    card = _ui(memory_redis)["open_card"]
    assert card["adaptation_id"] == "a1" and card["video"] is True
    assert _ui(memory_redis)["last_delivery_ms"] > 0


async def test_got_it_closes_the_card_and_resolves_the_state(memory_redis, sent, events):
    await ws._handle_ui_event(_event("section_entered", section_id="sec-A"), USER)
    await ws._deliver_adaptation(_result("sec-A"), USER, "s1", 5)
    await ws._handle_adaptation_interaction(
        {"type": "adaptation_interaction", "ts": 1, "data": {
            "adaptation_id": "a1", "action": "show_hint", "interaction": "accepted",
            "section_id": "sec-A",
        }},
        USER, "s1",
    )
    ui = _ui(memory_redis)
    assert ui["open_card"] is None
    assert "sec-A:confused" in ui["resolved"]


async def test_dismissing_credits_the_rung(memory_redis, sent, events):
    await ws._handle_ui_event(_event("section_entered", section_id="sec-A"), USER)
    await ws._handle_adaptation_interaction(
        {"type": "adaptation_interaction", "ts": 1, "data": {
            "adaptation_id": "a1", "action": "show_breakdown", "interaction": "dismissed",
            "section_id": "sec-A",
        }},
        USER, "s1",
    )
    ui = _ui(memory_redis)
    assert ui["rung_credit"] == {"sec-A:confused": 1}
    assert ui["dismissed_until_ms"] > 0
