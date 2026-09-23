"""Learner-requested help ("Still stuck" / "I'd rather move on") end to end through the graph.

The request bypasses the DETECTOR's restraints and nothing else: it still needs the adaptive arm,
it still climbs the same ladder, and it is recorded under its own names so it never mixes into the
detection or trial statistics.
"""

import pytest

import app.api.routes.ws as ws
from app.agents.nodes import content_adapter, pedagogical

pytestmark = pytest.mark.asyncio

SECTION_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def captured_events(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(ws, "emit_research_event", fake_emit)
    # The graph's nodes emit through the research logger directly; capture those too.
    monkeypatch.setattr(pedagogical, "emit_research_event", fake_emit)
    monkeypatch.setattr(content_adapter, "emit_research_event", fake_emit)
    return events


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    """No section resolver, no language model, no throttle carried between tests."""
    from app.services import content_context_service

    async def fake_build(section_id, _db):
        if not section_id:
            return {}
        return {"topic": "Pointers", "lesson": "Memory", "body": "A pointer holds an address.",
                "difficulty": "unknown", "section_id": SECTION_ID}

    monkeypatch.setattr(content_context_service, "build", fake_build)

    def no_llm():
        raise RuntimeError("no model in tests")

    monkeypatch.setattr(pedagogical, "get_chat_client", no_llm)
    monkeypatch.setattr(content_adapter, "get_chat_client", no_llm)
    ws._last_help_request_ms.clear()


def _request(kind="still_stuck"):
    return {"type": "help_request", "ts": 1, "data": {
        "request": kind, "section_id": SECTION_ID, "adaptation_id": "a1",
        "action": "show_hint", "cycle_number": 3,
    }}


def _of(events, event_type):
    return [e for e in events if e["event_type"] == event_type]


async def test_still_stuck_on_the_adaptive_arm_produces_the_next_help(captured_events):
    await ws._handle_help_request(_request(), "u-adaptive", "s1", None, "phase_b", "adaptive")

    requested = _of(captured_events, "help_requested")
    assert len(requested) == 1
    assert requested[0]["payload"]["affect_state"] == "confused"
    assert requested[0]["payload"]["from_adaptation_id"] == "a1"

    triggered = _of(captured_events, "adaptation_triggered")
    assert len(triggered) == 1
    assert triggered[0]["payload"]["action_type"] in {
        "show_hint", "show_breakdown", "show_alternative"
    }


async def test_move_on_climbs_the_boredom_ladder(captured_events):
    await ws._handle_help_request(
        _request("move_on"), "u-bored", "s1", None, "phase_b", "adaptive"
    )
    triggered = _of(captured_events, "adaptation_triggered")
    assert triggered and triggered[0]["payload"]["action_type"] in {
        "increase_difficulty", "skip_ahead"
    }


async def test_the_control_arm_gets_nothing(captured_events):
    await ws._handle_help_request(_request(), "u-control", "s1", None, "phase_b", "control")
    assert _of(captured_events, "adaptation_triggered") == []


async def test_an_unknown_request_is_dropped(captured_events):
    await ws._handle_help_request(
        _request("do_my_homework"), "u1", "s1", None, "phase_b", "adaptive"
    )
    assert captured_events == []


async def test_a_second_request_within_the_gap_is_dropped(captured_events):
    await ws._handle_help_request(_request(), "u-fast", "s1", None, "phase_b", "adaptive")
    await ws._handle_help_request(_request(), "u-fast", "s1", None, "phase_b", "adaptive")
    assert len(_of(captured_events, "help_requested")) == 1
