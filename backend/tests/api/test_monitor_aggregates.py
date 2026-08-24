"""GET /api/v1/monitor/aggregates — the Aggregate tab's data source.

The value of this endpoint is the gate-reason distribution: at a 0.70 threshold the gate
withholds on most cycles, and the reason breakdown is how you tell a correctly-conservative
gate from a mis-tuned one. So these tests assert the breakdown, not just the HTTP shape.
"""

from __future__ import annotations

import time

import pytest

from app.models.research_event import ResearchEvent

BASE = "/api/v1/monitor/aggregates"
NOW = int(time.time() * 1000)
HOUR = 3_600_000


def _ev(event_type: str, *, session: str = "s1", cycle: int = 0, ts: int | None = None, **payload):
    return ResearchEvent(
        event_type=event_type,
        learner_id="l1",
        session_id=session,
        cycle_number=cycle,
        timestamp=NOW - 60_000 if ts is None else ts,
        sequence_number=cycle,
        payload=payload or None,
    )


async def _seed(db):
    """A realistic-shaped window: mostly withheld cycles, two interventions, both fallback."""
    rows = [
        # gate decisions — the shape a calibrated 0.70 gate actually produces
        *[_ev("learner_profile_updated", cycle=i, adaptation_gate="state_not_actionable")
          for i in range(6)],
        *[_ev("learner_profile_updated", cycle=10 + i, adaptation_gate="low_confidence")
          for i in range(3)],
        _ev("learner_profile_updated", cycle=20, adaptation_gate="not_sustained"),
        _ev("learner_profile_updated", cycle=21, adaptation_gate="cooldown"),
        # an unrecognised reason must be surfaced, not silently dropped
        _ev("learner_profile_updated", cycle=22, adaptation_gate="some_future_reason"),
        # affect detections across both modalities
        _ev("behavioral_affect_detected", cycle=1, affect_state="engaged"),
        _ev("behavioral_affect_detected", cycle=2, affect_state="confused"),
        _ev("multimodal_affect_detected", cycle=2, affect_state="confused"),
        # two delivered adaptations, both from the deterministic fallback (vLLM unreachable)
        _ev("adaptation_delivered", cycle=23, action="show_hint", fallback=True),
        _ev("adaptation_delivered", cycle=30, action="show_breakdown", fallback=True),
        # a second session, so the session count is exercised
        _ev("learner_profile_updated", session="s2", cycle=0, adaptation_gate="low_confidence"),
        # outside the 24h window — must be excluded
        _ev("learner_profile_updated", session="s3", cycle=0, ts=NOW - 100 * HOUR,
            adaptation_gate="cooldown"),
    ]
    db.add_all(rows)
    await db.commit()


async def test_gate_reason_distribution(client, db, admin_headers):
    await _seed(db)
    r = await client.get(f"{BASE}?hours=24", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()

    g = body["gateReasons"]
    assert g["state_not_actionable"] == 6
    assert g["low_confidence"] == 4  # 3 in s1 + 1 in s2
    assert g["not_sustained"] == 1
    assert g["cooldown"] == 1  # the 100h-old row is outside the window

    # Unknown reasons are reported separately rather than dropped.
    assert body["gateReasonsUnknown"] == {"some_future_reason": 1}
    assert body["gatedCycles"] == 13


async def test_interventions_and_fallback_rate(client, db, admin_headers):
    await _seed(db)
    body = (await client.get(f"{BASE}?hours=24", headers=admin_headers)).json()

    iv = body["interventions"]
    assert iv["delivered"] == 2
    assert iv["fallback"] == 2
    # Every delivered adaptation was canned — this is what an unreachable vLLM looks like.
    assert iv["fallbackRate"] == 1.0
    assert iv["perHour"] == pytest.approx(2 / 24, abs=1e-3)


async def test_sessions_affect_and_window(client, db, admin_headers):
    await _seed(db)
    body = (await client.get(f"{BASE}?hours=24", headers=admin_headers)).json()

    assert body["sessions"] == 2  # s3 is out of window
    assert body["affectCounts"] == {"engaged": 1, "confused": 2}
    assert body["windowHours"] == 24
    assert body["startTs"] < body["endTs"]
    assert "confidence" in body and "insufficient_data" in body


async def test_empty_window_is_zeroes_not_an_error(client, admin_headers):
    body = (await client.get(f"{BASE}?hours=1", headers=admin_headers)).json()
    assert body["totalEvents"] == 0
    assert body["cycles"] == 0
    assert body["interventions"]["delivered"] == 0
    # No division by zero when nothing was delivered.
    assert body["interventions"]["fallbackRate"] is None
    # Every known reason still present as a zero, so the chart has a stable set of bars.
    assert set(body["gateReasons"]) == {
        "state_not_actionable", "low_confidence", "not_sustained", "cooldown",
    }
    assert all(v == 0 for v in body["gateReasons"].values())


async def test_hours_is_validated(client, admin_headers):
    assert (await client.get(f"{BASE}?hours=0", headers=admin_headers)).status_code == 422
    assert (await client.get(f"{BASE}?hours=721", headers=admin_headers)).status_code == 422


async def test_rbac_learner_forbidden(client, auth_headers):
    r = await client.get(BASE, headers=auth_headers)
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "FORBIDDEN"


async def test_rbac_designer_forbidden(client, designer_headers):
    assert (await client.get(BASE, headers=designer_headers)).status_code == 403


async def test_rbac_unauthenticated(client):
    assert (await client.get(BASE)).status_code in (401, 403)
