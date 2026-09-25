"""End to end: one learner's session through the real WebSocket endpoint.

Everything after the detector runs for real: the WebSocket handler, the compiled agent graph, the
profiler and adaptation gate, the delivery guard, the pedagogical agent and content adapter (on
their rule fallback, since no language model is reachable in tests), delivery, and the learner's
answers flowing back. Only the facial model's output is fixed, so the learner is reliably "bored",
and the section resolver is stubbed so no course fixtures are needed.

The journey is the list of problems a learner used to hit:
  1. a card arrives, tied to the section it was written for;
  2. while it is open, a still-bored learner is NOT sent another card on top of it;
  3. after "Got it", the same state in the same section is left alone;
  4. after moving to another section, a reading from a window that started on the old one is
     not acted on;
  5. "I'm stuck" gets help on the new section at any time, card or no card;
  6. a hidden tab is never interrupted.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

import app.agents.nodes.affect_detection as affect_detection
import app.agents.nodes.content_adapter as content_adapter
import app.agents.nodes.learner_profiler as learner_profiler
import app.agents.nodes.pedagogical as pedagogical
import app.api.routes.ws as ws_routes
from app.agents import delivery_guard
from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.services import content_context_service, redis_service
from app.services.connection_manager import connection_manager

SEC_A = "11111111-1111-1111-1111-11111111aaaa"
SEC_B = "11111111-1111-1111-1111-11111111bbbb"


@pytest.fixture
def journey(db: AsyncSession, monkeypatch):
    from app.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "SEED_ON_STARTUP", False)

    # Redis, in memory: the profile, the session state and the screen state all live here.
    store: dict = {}

    async def get_json(key):
        return store.get(key)

    async def set_json(key, value, ttl_seconds=None):
        store[key] = value

    monkeypatch.setattr(redis_service, "get_json", get_json)
    monkeypatch.setattr(redis_service, "set_json", set_json)

    # This learner is on the adaptive arm of Phase B.
    async def adaptive(_db, _user_id):
        return ("phase_b", "adaptive")

    monkeypatch.setattr(ws_routes, "_resolve_phase_group", adaptive)

    async def build(section_id, _db):
        return {"section_id": section_id, "topic": "Java money", "lesson": "Floating point",
                "body": "Doubles cannot represent 0.1 exactly.", "difficulty": "unknown"}

    monkeypatch.setattr(content_context_service, "build", build)

    # The deployed facial artifact: the geometry model (as `/health/pipeline` reports in prod).
    monkeypatch.setenv("AFFECT_MODEL_KIND", "geometry")

    # The facial model says: disengaged, 95% sure.
    async def bored(payload):
        # Like the real model: no frames, no reading (a help request carries no payload).
        if not (payload or {}).get("geometry"):
            return None
        return {"engagement_level": 1, "class_index": 1, "class_order": ["engaged", "disengaged"],
                "model_kind": "geometry", "label": "disengaged", "confidence": 0.95,
                "probs": [0.05, 0.95], "face_ratio": 1.0, "frames_scored": 10}

    monkeypatch.setattr(affect_detection, "detect_engagement", bored)

    # No language model in tests: the agents take their rule fallback immediately.
    def no_model():
        raise RuntimeError("no model in tests")

    monkeypatch.setattr(pedagogical, "get_chat_client", no_model)
    monkeypatch.setattr(content_adapter, "get_chat_client", no_model)

    # No section grace period: the test cannot wait 45 real seconds (grace is unit-tested).
    monkeypatch.setattr(delivery_guard, "SECTION_GRACE_MS", 0)

    # Capture every gate verdict, from the profiler's research event.
    verdicts: list[str] = []

    async def capture(event):
        if event.get("event_type") == "learner_profile_updated":
            verdicts.append(event["payload"]["adaptation_gate"])

    monkeypatch.setattr(learner_profiler, "emit_research_event", capture)

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, store, verdicts
    app.dependency_overrides.clear()
    connection_manager._sockets.clear()
    connection_manager._session_ids.clear()


def _facial(cycle: int, section: str) -> dict:
    return {"type": "facial_features", "ts": 1, "data": {
        "cycle_number": cycle, "capture_started_at": 0, "capture_ended_at": 1,
        "frames_captured": 10, "dropped_frames": 0,
        "dropped_reasons": {"no_face": 0, "low_confidence": 0},
        "frames_with_face": 10, "face_ratio": 1.0, "face_absent": False,
        "geometry": [[0.1] * 11 for _ in range(10)],
        "contract_version": 1, "geometry_contract_version": 1,
        "channel_order": [], "frames_per_cycle": 10, "section_id": section,
    }}


def _ui(event: str, **data) -> dict:
    return {"type": "ui_event", "ts": 1, "data": {"event": event, **data}}


def _exchange(ws, message: dict) -> list[dict]:
    """Send one message and return everything the server pushed while handling it.

    The handler processes one message at a time, so a heartbeat sent straight after is answered
    only once the first message is finished: everything before its ack belongs to the first.
    """
    ws.send_json(message)
    ws.send_json({"type": "heartbeat", "ts": 1, "data": {"seq": 1}})
    received = []
    while True:
        msg = ws.receive_json()
        if msg.get("type") == "heartbeat_ack":
            return received
        received.append(msg)


def _cards(messages: list[dict]) -> list[dict]:
    return [m for m in messages if m.get("type") == "adaptation"]


def test_a_learners_session_end_to_end(journey, test_user: User, monkeypatch):
    client, store, verdicts = journey
    token = create_access_token(str(test_user.id))

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        hello = ws.receive_json()
        assert hello["action"] in ("connected", "session_restored")
        assert hello["data"]["adaptive"] is True  # the page may offer "I'm stuck"

        _exchange(ws, _ui("section_entered", section_id=SEC_A))

        # 1. Bored for two cycles in a row on section A: one card, tied to section A.
        first = _cards(_exchange(ws, _facial(1, SEC_A)) + _exchange(ws, _facial(2, SEC_A)))
        assert len(first) == 1, verdicts
        card = first[0]
        assert card["section_id"] == SEC_A
        assert card["action"] == "increase_difficulty"

        # 2. Still bored while that card is open: nothing is sent on top of it. The 3-cycle
        #    cooldown covers cycles 3-4; from cycle 5 the cooldown has passed and it is the open
        #    card alone that holds the next one back (before this fix, cycle 5 sent a new card).
        assert _cards(_exchange(ws, _facial(3, SEC_A)) + _exchange(ws, _facial(4, SEC_A))) == []
        assert verdicts[-1] == "cooldown"
        assert _cards(_exchange(ws, _facial(5, SEC_A)) + _exchange(ws, _facial(6, SEC_A))) == []
        assert verdicts[-1] == delivery_guard.GATE_CARD_OPEN

        # 3. "Got it": the card closes, and bored-in-section-A is left alone for a while, even
        #    once the minimum spacing between cards has passed.
        _exchange(ws, {"type": "adaptation_interaction", "ts": 1, "data": {
            "adaptation_id": card["adaptation_id"], "action": card["action"],
            "interaction": "accepted", "section_id": SEC_A,
        }})
        monkeypatch.setattr(delivery_guard, "MIN_SPACING_MS", 0)
        assert _cards(_exchange(ws, _facial(8, SEC_A)) + _exchange(ws, _facial(9, SEC_A))) == []
        assert verdicts[-1] == delivery_guard.GATE_RESOLVED

        # 4. Move to section B. A window that STARTED on section A arrives afterwards: it is
        #    about the page the learner left, so it is not acted on.
        _exchange(ws, _ui("section_entered", section_id=SEC_B))
        assert _cards(_exchange(ws, _facial(13, SEC_A)) + _exchange(ws, _facial(14, SEC_A))) == []
        assert verdicts[-1] == delivery_guard.GATE_STALE_SECTION

        # 5. "I'm stuck" on section B, with no card on screen: help arrives, about section B.
        asked = _cards(_exchange(ws, {"type": "help_request", "ts": 1, "data": {
            "request": "still_stuck", "section_id": SEC_B, "cycle_number": 14,
        }}))
        assert len(asked) == 1
        assert asked[0]["section_id"] == SEC_B
        assert asked[0]["action"] == "show_hint"

        # 6. The learner switches tab. Bored readings on section B do not interrupt a hidden tab.
        _exchange(ws, {"type": "adaptation_interaction", "ts": 1, "data": {
            "adaptation_id": asked[0]["adaptation_id"], "action": "show_hint",
            "interaction": "dismissed", "section_id": SEC_B,
        }})
        _exchange(ws, _ui("visibility", visible=False))
        assert _cards(_exchange(ws, _facial(20, SEC_B)) + _exchange(ws, _facial(21, SEC_B))) == []
        assert verdicts[-1] == delivery_guard.GATE_PAGE_HIDDEN

    # The screen state the server kept for this learner reflects the whole journey.
    ui = store[f"ui:learner:{test_user.id}"]
    assert ui["section_id"] == SEC_B
    assert ui["page_hidden"] is True
    assert f"{SEC_A}:bored" in ui["resolved"]
