"""WebSocket endpoint integration tests (Story 4.1, Task 4.1).

Uses Starlette's TestClient (sync) which provides the `websocket_connect` context-manager
for in-process WS handshake testing.
"""

import json
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import Role, User
from app.services.connection_manager import (
    WS_CLOSE_AUTH_FAILED,
    WS_CLOSE_SUPERSEDED,
    connection_manager,
)


@pytest.fixture(autouse=True)
def _reset_manager_after_each_test():
    """ConnectionManager is a module-level singleton — clear state between tests."""
    yield
    connection_manager._sockets.clear()
    connection_manager._session_ids.clear()


@pytest.fixture
def sync_client(db: AsyncSession, monkeypatch):
    """Sync TestClient with DB override — required for the WS handshake."""

    # The app's lifespan runs startup seeding against the prod DB if SEED_ON_STARTUP is set
    # in .env. Disable it for tests so the lifespan is a no-op.
    from app.core.config import settings as app_settings
    monkeypatch.setattr(app_settings, "SEED_ON_STARTUP", False)

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _make_expired_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        "iat": datetime.now(timezone.utc) - timedelta(minutes=2),
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _make_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=1),
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def test_connects_with_valid_learner_token(sync_client: TestClient, test_user: User):
    token = create_access_token(str(test_user.id))
    with sync_client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "system"
        assert msg["action"] in {"connected", "session_restored"}
        assert isinstance(msg["ts"], int)


def test_missing_token_closes_4401_missing_token(sync_client: TestClient):
    with pytest.raises(WebSocketDisconnect) as exc:
        with sync_client.websocket_connect("/api/v1/ws"):
            pass
    assert exc.value.code == WS_CLOSE_AUTH_FAILED
    assert exc.value.reason == "missing_token"


def test_invalid_token_closes_4401(sync_client: TestClient):
    with pytest.raises(WebSocketDisconnect) as exc:
        with sync_client.websocket_connect("/api/v1/ws?token=not-a-real-jwt"):
            pass
    assert exc.value.code == WS_CLOSE_AUTH_FAILED
    assert exc.value.reason in {"invalid_token", "expired_token"}


def test_expired_token_closes_4401_expired(sync_client: TestClient, test_user: User):
    token = _make_expired_token(str(test_user.id))
    with pytest.raises(WebSocketDisconnect) as exc:
        with sync_client.websocket_connect(f"/api/v1/ws?token={token}"):
            pass
    assert exc.value.code == WS_CLOSE_AUTH_FAILED
    assert exc.value.reason == "expired_token"


def test_refresh_token_rejected_as_invalid(sync_client: TestClient, test_user: User):
    token = _make_refresh_token(str(test_user.id))
    with pytest.raises(WebSocketDisconnect) as exc:
        with sync_client.websocket_connect(f"/api/v1/ws?token={token}"):
            pass
    assert exc.value.code == WS_CLOSE_AUTH_FAILED
    assert exc.value.reason == "invalid_token"


def test_designer_role_rejected(sync_client: TestClient, test_designer: User):
    token = create_access_token(str(test_designer.id))
    with pytest.raises(WebSocketDisconnect) as exc:
        with sync_client.websocket_connect(f"/api/v1/ws?token={token}"):
            pass
    assert exc.value.code == WS_CLOSE_AUTH_FAILED
    assert exc.value.reason == "role_not_authorized"


def test_admin_role_rejected(sync_client: TestClient, test_admin: User):
    token = create_access_token(str(test_admin.id))
    with pytest.raises(WebSocketDisconnect) as exc:
        with sync_client.websocket_connect(f"/api/v1/ws?token={token}"):
            pass
    assert exc.value.code == WS_CLOSE_AUTH_FAILED
    assert exc.value.reason == "role_not_authorized"


def test_heartbeat_receives_ack(sync_client: TestClient, test_user: User):
    token = create_access_token(str(test_user.id))
    with sync_client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        # Discard the initial system.connected message.
        _ = ws.receive_json()
        ws.send_json({"type": "heartbeat", "ts": 1234, "data": {"seq": 42}})
        ack = ws.receive_json()
        assert ack["type"] == "heartbeat_ack"
        assert ack["data"]["seq"] == 42
        assert "server_ts" in ack["data"]


def test_malformed_json_does_not_close(sync_client: TestClient, test_user: User):
    token = create_access_token(str(test_user.id))
    with sync_client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        _ = ws.receive_json()
        # Send raw garbage; connection must stay open.
        ws.send_text("{not json")
        # Then send a valid heartbeat and confirm we still get an ack.
        ws.send_json({"type": "heartbeat", "ts": 2000, "data": {"seq": 7}})
        ack = ws.receive_json()
        assert ack["type"] == "heartbeat_ack"
        assert ack["data"]["seq"] == 7


def test_missing_type_field_does_not_close(sync_client: TestClient, test_user: User):
    token = create_access_token(str(test_user.id))
    with sync_client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        _ = ws.receive_json()
        ws.send_json({"ts": 1, "data": {}})  # missing "type"
        # Connection still alive: heartbeat round-trip works.
        ws.send_json({"type": "heartbeat", "ts": 2, "data": {"seq": 1}})
        ack = ws.receive_json()
        assert ack["type"] == "heartbeat_ack"


def test_unknown_type_does_not_close(sync_client: TestClient, test_user: User):
    token = create_access_token(str(test_user.id))
    with sync_client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        _ = ws.receive_json()
        ws.send_json({"type": "future_type_from_story_4_2", "ts": 3, "data": {}})
        ws.send_json({"type": "heartbeat", "ts": 4, "data": {"seq": 9}})
        ack = ws.receive_json()
        assert ack["type"] == "heartbeat_ack"


def test_second_tab_supersedes_first(sync_client: TestClient, test_user: User):
    """AC #11: second connection from same user closes the first with code 4001."""
    token = create_access_token(str(test_user.id))
    with sync_client.websocket_connect(f"/api/v1/ws?token={token}") as ws_a:
        _ = ws_a.receive_json()  # discard system.connected on ws_a
        with sync_client.websocket_connect(f"/api/v1/ws?token={token}") as ws_b:
            _ = ws_b.receive_json()  # discard system.connected on ws_b
            # ws_a should now receive a close with code 4001.
            with pytest.raises(WebSocketDisconnect) as exc:
                ws_a.receive_json()
            assert exc.value.code == WS_CLOSE_SUPERSEDED


# --- Session restore on reconnect ---
#
# `_load_session_state` returned a hardcoded None for every learner, so the `session_restored`
# branch was unreachable and the message documented in `routes/README.md` was one the server could
# never send — while the client half was complete and waiting for it (a wire type, a type guard,
# a store action, and tests for all three). Every reconnect looked like a brand-new session.


def test_session_state_omits_the_affect_inference(monkeypatch):
    """The payload goes straight to the browser, so it must not carry detected affect.

    `architecture.md` lists showing a learner their affect state as an anti-pattern. The message
    contract has an optional `last_affect_state` field; leaving it unset is what keeps the rule
    enforced here rather than relying on the client to ignore what it is sent.
    """
    import asyncio

    from app.api.routes import ws as ws_module

    written: dict = {}

    async def fake_set_json(key, value, ttl_seconds=None):
        written["key"] = key
        written["value"] = value
        written["ttl"] = ttl_seconds

    monkeypatch.setattr(ws_module.redis_service, "set_json", fake_set_json)

    asyncio.run(
        ws_module._save_session_state(
            "learner-1", section_id="sec-9", phase="phase_b", group="adaptive"
        )
    )

    assert written["key"] == "session:learner:learner-1"
    assert written["value"] == {
        "current_section_id": "sec-9",
        "phase": "phase_b",
        "group": "adaptive",
        # Kept so a server restart does not start the learner's session (and ladder) over.
        "session_id": None,
    }
    assert "last_affect_state" not in written["value"]
    assert written["ttl"] == ws_module._SESSION_STATE_TTL_SECONDS


def test_no_section_means_nothing_is_remembered(monkeypatch):
    """A message with no position tells us nothing about where the learner is."""
    import asyncio

    from app.api.routes import ws as ws_module

    calls = {"n": 0}

    async def fake_set_json(key, value, ttl_seconds=None):
        calls["n"] += 1

    monkeypatch.setattr(ws_module.redis_service, "set_json", fake_set_json)

    asyncio.run(
        ws_module._save_session_state("learner-1", section_id=None, phase="phase_a", group="control")
    )

    assert calls["n"] == 0


def test_a_cache_outage_costs_the_banner_and_nothing_else(monkeypatch):
    """Redis being down must not break the handshake — it just means no restore."""
    import asyncio

    from app.api.routes import ws as ws_module

    async def boom(key):
        raise RuntimeError("redis is gone")

    monkeypatch.setattr(ws_module.redis_service, "get_json", boom)

    assert asyncio.run(ws_module._load_session_state("learner-1")) is None


def test_stored_state_is_returned_for_restoration(monkeypatch):
    import asyncio

    from app.api.routes import ws as ws_module

    async def fake_get_json(key):
        assert key == "session:learner:learner-1"
        return {"current_section_id": "sec-9", "phase": "phase_b", "group": "adaptive"}

    monkeypatch.setattr(ws_module.redis_service, "get_json", fake_get_json)

    state = asyncio.run(ws_module._load_session_state("learner-1"))
    assert state["current_section_id"] == "sec-9"
