"""Tests for the pilot-study admin API (Story 6.1 AC5/AC8).

Covers: admin happy paths (assign/list/lock, phase get/set), 403 for non-admin, 409 for a
locked re-assign, 422 for an invalid enum value, 404 for an unknown user, and the
`phase_transition` event on a real phase change (emit monkeypatched at the service).
"""

import uuid

import pytest

import app.services.study_service as ss
from app.core.security import create_access_token

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/admin/study"


@pytest.fixture
def captured_events(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(ss, "emit_research_event", fake_emit)
    return events


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


# ── group assignment ─────────────────────────────────────────────────────────--

async def test_admin_assign_group(client, test_admin, test_user):
    resp = await client.post(
        f"{BASE}/groups",
        json={"userId": str(test_user.id), "group": "adaptive"},
        headers=_headers(test_admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["group"] == "adaptive"
    assert body["userId"] == str(test_user.id)
    assert body["lockedAt"] is None


async def test_assign_group_forbidden_for_learner(client, test_user):
    resp = await client.post(
        f"{BASE}/groups",
        json={"userId": str(test_user.id), "group": "adaptive"},
        headers=_headers(test_user),
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "FORBIDDEN"


async def test_assign_group_invalid_value_422(client, test_admin, test_user):
    resp = await client.post(
        f"{BASE}/groups",
        json={"userId": str(test_user.id), "group": "nonsense"},
        headers=_headers(test_admin),
    )
    assert resp.status_code == 422


async def test_assign_group_unknown_user_404(client, test_admin):
    resp = await client.post(
        f"{BASE}/groups",
        json={"userId": str(uuid.uuid4()), "group": "control"},
        headers=_headers(test_admin),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "USER_NOT_FOUND"


async def test_locked_reassign_returns_409(client, test_admin, test_user):
    h = _headers(test_admin)
    await client.post(
        f"{BASE}/groups",
        json={"userId": str(test_user.id), "group": "adaptive"},
        headers=h,
    )
    lock = await client.post(f"{BASE}/groups/lock", headers=h)
    assert lock.status_code == 200
    assert lock.json()["lockedCount"] == 1

    resp = await client.post(
        f"{BASE}/groups",
        json={"userId": str(test_user.id), "group": "control"},
        headers=h,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "GROUP_LOCKED"


async def test_list_groups_paginated(client, test_admin, test_user, test_designer):
    h = _headers(test_admin)
    await client.post(
        f"{BASE}/groups", json={"userId": str(test_user.id), "group": "adaptive"}, headers=h
    )
    await client.post(
        f"{BASE}/groups", json={"userId": str(test_designer.id), "group": "control"}, headers=h
    )
    resp = await client.get(f"{BASE}/groups", headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


async def test_list_groups_forbidden_for_designer(client, test_designer):
    resp = await client.get(f"{BASE}/groups", headers=_headers(test_designer))
    assert resp.status_code == 403


# ── phase ─────────────────────────────────────────────────────────────────────-

async def test_get_phase_default(client, test_admin):
    resp = await client.get(f"{BASE}/phase", headers=_headers(test_admin))
    assert resp.status_code == 200
    body = resp.json()
    assert body["phase"] == "phase_a"
    assert body["transitionedAt"] is None


async def test_set_phase_transition_and_event(client, test_admin, captured_events):
    h = _headers(test_admin)
    resp = await client.post(f"{BASE}/phase", json={"phase": "phase_b"}, headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["from"] == "phase_a"
    assert body["to"] == "phase_b"
    assert body["transitionedAt"] is not None

    # GET reflects the new phase.
    get_resp = await client.get(f"{BASE}/phase", headers=h)
    assert get_resp.json()["phase"] == "phase_b"

    # phase_transition event emitted with the admin as actor.
    transitions = [e for e in captured_events if e["event_type"] == "phase_transition"]
    assert len(transitions) == 1
    assert transitions[0]["payload"]["actor_id"] == str(test_admin.id)


async def test_set_phase_noop_no_event(client, test_admin, captured_events):
    resp = await client.post(f"{BASE}/phase", json={"phase": "phase_a"}, headers=_headers(test_admin))
    assert resp.status_code == 200
    assert resp.json()["from"] == resp.json()["to"] == "phase_a"
    assert [e for e in captured_events if e["event_type"] == "phase_transition"] == []


async def test_set_phase_invalid_value_422(client, test_admin):
    resp = await client.post(
        f"{BASE}/phase", json={"phase": "phase_c"}, headers=_headers(test_admin)
    )
    assert resp.status_code == 422


async def test_set_phase_forbidden_for_learner(client, test_user):
    resp = await client.post(
        f"{BASE}/phase", json={"phase": "phase_b"}, headers=_headers(test_user)
    )
    assert resp.status_code == 403
