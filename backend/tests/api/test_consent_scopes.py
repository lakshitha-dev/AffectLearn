"""Consent scopes, withdrawal, server-side enforcement and erasure of cached state (migration 032).

The browser only captures after consent, but the server is where consent has to hold: before this,
nothing on the WebSocket path read `consent_given_at` or `webcam_enabled`, so capture from a learner
who had not consented, or had switched the camera off, was processed and stored like any other.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from starlette.testclient import TestClient

from app.services.consent import CURRENT_CONSENT_VERSION, ConsentState, normalise_scopes

CONSENT_URL = "/api/v1/auth/consent"
WITHDRAW_URL = "/api/v1/auth/consent/withdraw"


# ── the consent record ──────────────────────────────────────────────────────────


class TestConsentRecord:
    async def test_records_version_and_scopes(self, client: AsyncClient, test_user, auth_headers):
        resp = await client.post(CONSENT_URL, headers=auth_headers, json={
            "consentGiven": True, "consentVersion": "v-test",
            "scopes": {"behavioural": True, "rawInteraction": True},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["consentVersion"] == "v-test"
        assert data["consentScopes"] == {"behavioural": True, "rawInteraction": True}
        assert data["consentWithdrawnAt"] is None

    async def test_an_older_client_gets_the_current_text_and_default_scopes(
        self, client: AsyncClient, test_user, auth_headers
    ):
        data = (await client.post(
            CONSENT_URL, headers=auth_headers, json={"consentGiven": True}
        )).json()
        assert data["consentVersion"] == CURRENT_CONSENT_VERSION
        # Raw-event storage is opt-in: never on unless the learner ticked it.
        assert data["consentScopes"] == {"behavioural": True, "rawInteraction": False}

    async def test_changing_scopes_keeps_the_original_consent_time(
        self, client: AsyncClient, test_user, auth_headers
    ):
        first = (await client.post(CONSENT_URL, headers=auth_headers, json={
            "consentGiven": True, "scopes": {"behavioural": True, "rawInteraction": True},
        })).json()
        second = (await client.post(CONSENT_URL, headers=auth_headers, json={
            "consentGiven": True, "scopes": {"behavioural": True, "rawInteraction": False},
        })).json()
        assert second["consentGivenAt"] == first["consentGivenAt"]
        assert second["consentScopes"]["rawInteraction"] is False

    async def test_withdraw_then_consent_again_is_a_new_agreement(
        self, client: AsyncClient, test_user, auth_headers
    ):
        await client.post(CONSENT_URL, headers=auth_headers, json={"consentGiven": True})
        withdrawn = (await client.post(WITHDRAW_URL, headers=auth_headers)).json()
        assert withdrawn["consentWithdrawnAt"] is not None
        again = (await client.post(
            CONSENT_URL, headers=auth_headers, json={"consentGiven": True}
        )).json()
        assert again["consentWithdrawnAt"] is None

    async def test_withdraw_is_learner_only(self, client: AsyncClient, designer_headers):
        resp = await client.post(WITHDRAW_URL, headers=designer_headers)
        assert resp.status_code == 403


# ── what may be captured ────────────────────────────────────────────────────────


def _user(**kw):
    base = dict(consent_given_at=datetime.now(timezone.utc), consent_withdrawn_at=None,
                webcam_enabled=True, consent_scopes=None)
    return SimpleNamespace(**{**base, **kw})


class TestConsentState:
    def test_a_consented_learner_may_be_captured(self):
        state = ConsentState.of(_user())
        assert all(state.refusal(t) is None for t in (
            "facial_features", "behavioral_window", "performance_window",
            "self_report", "adaptation_probe"))

    def test_no_consent_refuses_every_capture_type(self):
        state = ConsentState.of(_user(consent_given_at=None))
        assert state.refusal("facial_features") == "no_consent"
        assert state.refusal("behavioral_window") == "no_consent"
        assert state.refusal("self_report") == "no_consent"

    def test_withdrawal_refuses_capture(self):
        state = ConsentState.of(_user(consent_withdrawn_at=datetime.now(timezone.utc)))
        assert state.refusal("behavioral_window") == "no_consent"

    def test_camera_off_refuses_facial_only(self):
        state = ConsentState.of(_user(webcam_enabled=False))
        assert state.refusal("facial_features") == "webcam_not_consented"
        assert state.refusal("behavioral_window") is None

    def test_behavioural_scope_off_refuses_behavioural_windows(self):
        state = ConsentState.of(_user(consent_scopes={"behavioural": False}))
        assert state.refusal("behavioral_window") == "behavioural_not_consented"
        assert state.refusal("performance_window") == "behavioural_not_consented"
        assert state.refusal("facial_features") is None

    def test_non_capture_messages_are_not_checked(self):
        state = ConsentState.of(_user(consent_given_at=None))
        for msg in ("heartbeat", "ui_event", "help_request", "adaptation_interaction"):
            assert state.refusal(msg) is None

    def test_raw_interaction_is_opt_in(self):
        assert ConsentState.of(_user()).raw_interaction is False
        assert ConsentState.of(_user(consent_scopes={"raw_interaction": True})).raw_interaction
        assert not ConsentState.of(_user(
            consent_scopes={"raw_interaction": True}, consent_given_at=None)).raw_interaction

    def test_unknown_scopes_are_ignored(self):
        assert normalise_scopes({"behavioural": False, "video": True}) == {
            "behavioural": False, "raw_interaction": False}


# ── enforcement on the real endpoint ────────────────────────────────────────────


@pytest.fixture
def ws_client(db, monkeypatch):
    import app.api.routes.ws as ws_routes
    from app.core.config import settings as app_settings
    from app.core.deps import get_db
    from app.main import app
    from app.services.connection_manager import connection_manager

    monkeypatch.setattr(app_settings, "SEED_ON_STARTUP", False)
    handled: list[str] = []

    async def record_facial(*args, **kwargs):
        handled.append("facial_features")

    async def record_behavioral(*args, **kwargs):
        handled.append("behavioral_window")

    monkeypatch.setattr(ws_routes, "_handle_facial_features", record_facial)
    monkeypatch.setattr(ws_routes, "_handle_behavioral_window", record_behavioral)

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, handled
    app.dependency_overrides.clear()
    connection_manager._sockets.clear()
    connection_manager._session_ids.clear()


def _send_capture(client, user):
    from app.core.security import create_access_token

    token = create_access_token(str(user.id))
    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"type": "facial_features", "ts": 1, "data": {"cycle_number": 1}})
        ws.send_json({"type": "behavioral_window", "ts": 1, "data": {"cycle_number": 1}})
        ws.send_json({"type": "heartbeat", "ts": 1, "data": {"seq": 1}})
        while ws.receive_json().get("type") != "heartbeat_ack":
            pass


def test_capture_from_a_learner_without_consent_is_dropped(ws_client, test_user):
    client, handled = ws_client
    _send_capture(client, test_user)
    assert handled == []


def test_a_consented_learner_is_captured(ws_client, consented_user):
    client, handled = ws_client
    _send_capture(client, consented_user)
    assert handled == ["facial_features", "behavioral_window"]


@pytest.fixture
async def camera_off_user(db, consented_user):
    consented_user.webcam_enabled = False
    await db.commit()
    await db.refresh(consented_user)
    return consented_user


def test_camera_off_drops_facial_but_keeps_behavioural(ws_client, camera_off_user):
    client, handled = ws_client
    _send_capture(client, camera_off_user)
    assert handled == ["behavioral_window"]


# ── erasure reaches Redis and the queued stream ─────────────────────────────────


async def test_erasure_clears_cached_state_and_marks_the_learner(monkeypatch):
    from app.services import data_rights_service, redis_service

    deleted: list = []
    marked: dict = {}

    async def fake_delete_keys(*keys):
        deleted.extend(keys)
        return len(keys)

    async def fake_delete_matching(pattern):
        deleted.append(pattern)
        return 2

    async def fake_set_str(key, value, ttl_seconds=None):
        marked[key] = value
        return True

    monkeypatch.setattr(redis_service, "delete_keys", fake_delete_keys)
    monkeypatch.setattr(redis_service, "delete_matching", fake_delete_matching)
    monkeypatch.setattr(redis_service, "set_str", fake_set_str)

    removed = await data_rights_service.forget_in_redis("u-1")
    assert removed == 5
    assert set(deleted) == {"profile:learner:u-1", "session:learner:u-1", "ui:learner:u-1",
                            "activity:u-1:*"}
    assert marked == {"research:erased:u-1": "1"}


async def test_worker_drops_queued_events_of_an_erased_learner(monkeypatch, db):
    from sqlalchemy import select

    from app.models.research_event import ResearchEvent
    from app.services import research_worker

    entries = [
        ("1-0", {"event_type": "a", "learner_id": "gone", "session_id": "s", "timestamp": 1,
                 "event_id": "e-1"}),
        ("2-0", {"event_type": "a", "learner_id": "kept", "session_id": "s", "timestamp": 2,
                 "event_id": "e-2"}),
    ]

    async def fake_read(stream, count=100, last_id="0"):
        return entries

    async def fake_exists(key):
        return key == "research:erased:gone"

    monkeypatch.setattr(research_worker.redis_service, "stream_read", fake_read)
    monkeypatch.setattr(research_worker.redis_service, "exists", fake_exists)

    last_id, inserted = await research_worker.drain_once(db)
    assert (last_id, inserted) == ("2-0", 1)
    learners = (await db.execute(select(ResearchEvent.learner_id))).scalars().all()
    assert learners == ["kept"]
