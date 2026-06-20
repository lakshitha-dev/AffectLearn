"""Tests for the admin research export/query API (Story 6.5 AC4/AC5/AC6).

Covers: admin 200 + camelCase + sequence ordering; each filter param narrows; non-admin
(learner/course_designer) gets 403; gaps endpoint returns `{sessionId: [missingSeqs]}`;
phase-a-dataset returns behavioral + self_report phase_a rows. Rows are seeded directly via the
model (no live Redis/Postgres — the worker pipeline is exercised elsewhere).
"""

import pytest

from app.models.research_event import ResearchEvent

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/admin/research"
TS0 = 1_700_000_000_000


async def _seed(db):
    rows = [
        ResearchEvent(event_type="behavioral_affect_detected", learner_id="u1", session_id="s1",
                      cycle_number=1, timestamp=TS0 + 1, sequence_number=1, phase="phase_a",
                      group="control", payload={"event_counts": {"keystroke_count": 5}}),
        ResearchEvent(event_type="self_report", learner_id="u1", session_id="s1",
                      cycle_number=1, timestamp=TS0 + 2, sequence_number=2, phase="phase_a",
                      group="control", payload={"affect": "engaged", "skipped": False}),
        # seq 3 missing -> gap on s1
        ResearchEvent(event_type="section_completed", learner_id="u1", session_id="s1",
                      cycle_number=0, timestamp=TS0 + 4, sequence_number=4, phase="phase_a",
                      group="control", payload={"section_id": "sec-1"}),
        ResearchEvent(event_type="behavioral_affect_detected", learner_id="u2", session_id="s2",
                      cycle_number=1, timestamp=TS0 + 10, sequence_number=1, phase="phase_b",
                      group="adaptive", payload={"event_counts": {}}),
        ResearchEvent(event_type="self_report", learner_id="u2", session_id="s2",
                      cycle_number=1, timestamp=TS0 + 11, sequence_number=2, phase="phase_b",
                      group="adaptive", payload={"affect": "confused", "skipped": False}),
    ]
    db.add_all(rows)
    await db.commit()


# ── auth ──────────────────────────────────────────────────────────────────────

async def test_events_requires_admin_learner_403(client, db, auth_headers):
    await _seed(db)
    resp = await client.get(f"{BASE}/events", headers=auth_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "FORBIDDEN"


async def test_events_requires_admin_designer_403(client, db, designer_headers):
    await _seed(db)
    resp = await client.get(f"{BASE}/events", headers=designer_headers)
    assert resp.status_code == 403


async def test_events_unauthenticated_401_or_403(client, db):
    await _seed(db)
    resp = await client.get(f"{BASE}/events")
    assert resp.status_code in (401, 403)


# ── events: ordering + envelope ─────────────────────────────────────────────────

async def test_events_admin_200_camelcase_ordered(client, db, admin_headers):
    await _seed(db)
    resp = await client.get(f"{BASE}/events", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["page"] == 1
    assert "pageSize" in body  # camelCase envelope
    items = body["items"]
    # full camelCase envelope present on each item
    first = items[0]
    for key in ("id", "eventType", "learnerId", "sessionId", "cycleNumber",
                "timestamp", "sequenceNumber", "phase", "group", "payload"):
        assert key in first
    # ordering: within s1 the sequence numbers are monotonic (1,2,4)
    s1_seqs = [it["sequenceNumber"] for it in items if it["sessionId"] == "s1"]
    assert s1_seqs == [1, 2, 4]


# ── events: filters ─────────────────────────────────────────────────────────────

async def test_events_filter_phase(client, db, admin_headers):
    await _seed(db)
    resp = await client.get(f"{BASE}/events?phase=phase_b", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert all(it["phase"] == "phase_b" for it in body["items"])


async def test_events_filter_group(client, db, admin_headers):
    await _seed(db)
    resp = await client.get(f"{BASE}/events?group=adaptive", headers=admin_headers)
    assert resp.json()["total"] == 2


async def test_events_filter_learner_and_session(client, db, admin_headers):
    await _seed(db)
    r1 = await client.get(f"{BASE}/events?learnerId=u1", headers=admin_headers)
    assert r1.json()["total"] == 3
    r2 = await client.get(f"{BASE}/events?sessionId=s2", headers=admin_headers)
    assert r2.json()["total"] == 2


async def test_events_filter_event_type_comma_list(client, db, admin_headers):
    await _seed(db)
    resp = await client.get(
        f"{BASE}/events?eventType=self_report,section_completed", headers=admin_headers
    )
    assert resp.status_code == 200
    types = {it["eventType"] for it in resp.json()["items"]}
    assert types == {"self_report", "section_completed"}


async def test_events_filter_time_range(client, db, admin_headers):
    await _seed(db)
    resp = await client.get(
        f"{BASE}/events?startTs={TS0 + 10}&endTs={TS0 + 11}", headers=admin_headers
    )
    assert resp.json()["total"] == 2


async def test_events_pagination(client, db, admin_headers):
    await _seed(db)
    resp = await client.get(f"{BASE}/events?page=1&pageSize=2", headers=admin_headers)
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["pageSize"] == 2


# ── gaps ─────────────────────────────────────────────────────────────────────--

async def test_gaps_returns_missing_sequences(client, db, admin_headers):
    await _seed(db)
    resp = await client.get(f"{BASE}/events/gaps", headers=admin_headers)
    assert resp.status_code == 200
    gaps = resp.json()["gaps"]
    assert gaps["s1"] == [3]
    assert "s2" not in gaps


async def test_gaps_requires_admin(client, db, auth_headers):
    await _seed(db)
    resp = await client.get(f"{BASE}/events/gaps", headers=auth_headers)
    assert resp.status_code == 403


# ── phase-a-dataset ─────────────────────────────────────────────────────────────

async def test_phase_a_dataset_returns_behavioral_and_self_report(client, db, admin_headers):
    await _seed(db)
    resp = await client.get(f"{BASE}/phase-a-dataset", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    types = {it["eventType"] for it in body["items"]}
    assert types <= {"behavioral_affect_detected", "self_report"}
    assert all(it["phase"] == "phase_a" for it in body["items"])
    # s1 (phase_a) behavioral + self_report; the phase_b s2 rows are excluded.
    assert all(it["sessionId"] != "s2" for it in body["items"])
    assert body["total"] == 2


async def test_phase_a_dataset_requires_admin(client, db, designer_headers):
    await _seed(db)
    resp = await client.get(f"{BASE}/phase-a-dataset", headers=designer_headers)
    assert resp.status_code == 403
