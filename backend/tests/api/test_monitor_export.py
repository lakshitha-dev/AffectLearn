"""GET /api/v1/monitor/export.csv — the first CSV the backend has ever produced."""

from __future__ import annotations

import csv
import io
import time

from app.models.research_event import ResearchEvent
from app.services.monitor_export_service import COLUMNS

BASE = "/api/v1/monitor/export.csv"
NOW = int(time.time() * 1000)
HOUR = 3_600_000


def _ev(event_type: str, *, session: str = "s1", cycle: int = 0, seq: int = 0,
        ts: int | None = None, **payload):
    return ResearchEvent(
        event_type=event_type,
        learner_id="l1",
        session_id=session,
        cycle_number=cycle,
        timestamp=NOW - 60_000 if ts is None else ts,
        sequence_number=seq,
        phase="phase_b",
        group="adaptive",
        payload=payload or None,
    )


async def _seed(db):
    db.add_all([
        _ev("behavioral_affect_detected", cycle=1, seq=1, affect_state="engaged",
            affect_confidence=0.98, p_confused=0.02, model_kind="aggregate_confusion_gbdt"),
        _ev("facial_affect_detected", cycle=1, seq=2, affect_state="engaged",
            affect_confidence=0.55, probs=[0.45, 0.55], model_kind="binary_confusion"),
        _ev("learner_profile_updated", cycle=1, seq=3, affect_state="engaged",
            adaptation_gate="state_not_actionable"),
        _ev("adaptation_delivered", cycle=2, seq=4, action="show_hint", fallback=True),
        _ev("behavioral_affect_detected", session="s2", cycle=1, seq=1, affect_state="confused",
            affect_confidence=0.72, p_confused=0.72),
        # Outside the 24h window.
        _ev("behavioral_affect_detected", session="s3", cycle=1, seq=1, ts=NOW - 100 * HOUR,
            affect_state="engaged"),
    ])
    await db.commit()


def _parse(text: str):
    return list(csv.reader(io.StringIO(text)))


async def test_header_and_one_row_per_event(client, db, admin_headers):
    await _seed(db)
    r = await client.get(f"{BASE}?hours=24", headers=admin_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")

    rows = _parse(r.text)
    assert rows[0] == list(COLUMNS)
    assert len(rows) == 1 + 5  # header + the 5 in-window events (s3 excluded)


async def test_flattens_the_analysable_payload_fields(client, db, admin_headers):
    await _seed(db)
    rows = _parse((await client.get(f"{BASE}?hours=24", headers=admin_headers)).text)
    idx = {c: i for i, c in enumerate(rows[0])}
    body = rows[1:]

    beh = next(r for r in body if r[idx["event_type"]] == "behavioral_affect_detected"
               and r[idx["session_id"]] == "s1")
    assert beh[idx["affect_state"]] == "engaged"
    assert beh[idx["p_confused"]] == "0.02"
    assert beh[idx["model_kind"]] == "aggregate_confusion_gbdt"
    assert beh[idx["phase"]] == "phase_b"
    assert beh[idx["group"]] == "adaptive"
    assert beh[idx["iso_time"]].endswith("+00:00")

    # The gate reason is the field that makes a withheld cycle analysable.
    prof = next(r for r in body if r[idx["event_type"]] == "learner_profile_updated")
    assert prof[idx["gate_reason"]] == "state_not_actionable"

    dlv = next(r for r in body if r[idx["event_type"]] == "adaptation_delivered")
    assert dlv[idx["action"]] == "show_hint"
    assert dlv[idx["fallback"]] == "True"


async def test_recovers_p_confused_from_probs_for_older_rows(client, db, admin_headers):
    """Rows written before p_confused was emitted still carry the softmax."""
    await _seed(db)
    rows = _parse((await client.get(f"{BASE}?hours=24", headers=admin_headers)).text)
    idx = {c: i for i, c in enumerate(rows[0])}
    fac = next(r for r in rows[1:] if r[idx["event_type"]] == "facial_affect_detected")
    assert fac[idx["p_confused"]] == "0.55"


async def test_session_and_event_type_filters(client, db, admin_headers):
    await _seed(db)
    rows = _parse((await client.get(f"{BASE}?hours=24&session_id=s2", headers=admin_headers)).text)
    assert len(rows) == 2  # header + 1
    assert rows[1][2] == "s2"

    rows = _parse((await client.get(
        f"{BASE}?hours=24&event_types=adaptation_delivered", headers=admin_headers)).text)
    assert len(rows) == 2
    assert rows[1][6] == "adaptation_delivered"


async def test_empty_window_still_returns_a_header(client, admin_headers):
    rows = _parse((await client.get(f"{BASE}?hours=1", headers=admin_headers)).text)
    assert rows == [list(COLUMNS)]


async def test_attachment_filename_and_no_store(client, admin_headers):
    r = await client.get(f"{BASE}?hours=24", headers=admin_headers)
    assert "attachment" in r.headers["content-disposition"]
    assert ".csv" in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"


async def test_hours_validated(client, admin_headers):
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


# ── the trial columns ─────────────────────────────────────────────────────────────────

def _rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


async def test_the_trial_columns_are_appended_not_inserted(client, db, admin_headers):
    """Column ORDER is the contract for anyone already scripting against this download.

    Inserting a column mid-list silently shifts every field to its right, so a script reading by
    index would start filing confidence values under `model_kind` and never fail loudly.
    """
    assert COLUMNS[:18] == (
        "timestamp", "iso_time", "session_id", "learner_id", "cycle_number", "sequence_number",
        "event_type", "phase", "group", "affect_state", "confidence", "p_confused",
        "p_disengaged", "model_kind", "gate_reason", "forced_mode", "action", "fallback",
    )
    assert COLUMNS[18:] == (
        "section_id", "adaptation_id", "interaction", "probe_response", "arm",
    )


async def test_the_randomised_arm_reaches_the_flat_export(client, db, admin_headers):
    """Without this column the entire trial analysis has to go through the JSON events API.

    `arm` is what separates a delivered intervention from a withheld one, and the withheld set is
    the control the delivered set is compared against — so it is the single most load-bearing
    field in the file.
    """
    db.add_all([
        _ev("learner_profile_updated", cycle=5, seq=10, adaptation_gate="ok", arm="delivered"),
        _ev("learner_profile_updated", cycle=8, seq=11,
            adaptation_gate="withheld_random", arm="withheld"),
        _ev("learner_profile_updated", cycle=9, seq=12, adaptation_gate="low_confidence"),
    ])
    await db.commit()

    r = await client.get(f"{BASE}?hours=24", headers=admin_headers)
    assert r.status_code == 200
    rows = {row["gate_reason"]: row for row in _rows(r.text) if row["gate_reason"]}

    assert rows["ok"]["arm"] == "delivered"
    assert rows["withheld_random"]["arm"] == "withheld"
    # A cycle that never became eligible is in NEITHER arm; a blank here is not a control
    # observation and must not be read as one.
    assert rows["low_confidence"]["arm"] == ""


async def test_a_probe_response_is_flattened_and_a_decline_stays_distinct(client, db, admin_headers):
    """`dismissed` means the learner was asked and declined — not that the hint failed."""
    db.add_all([
        _ev("adaptation_probe", cycle=6, seq=20, adaptation_id="a1", response="helped"),
        _ev("adaptation_probe", cycle=7, seq=21, adaptation_id="a2",
            response=None, dismissed=True),
    ])
    await db.commit()

    r = await client.get(f"{BASE}?hours=24", headers=admin_headers)
    rows = {row["adaptation_id"]: row for row in _rows(r.text) if row["adaptation_id"]}

    assert rows["a1"]["probe_response"] == "helped"
    assert rows["a2"]["probe_response"] == "dismissed"


async def test_section_prefers_the_indexed_column_over_the_payload_copy(client, db, admin_headers):
    """The column is what the query API filters on; the payload copy exists only on older rows."""
    ev = _ev("adaptation_delivered", cycle=3, seq=30, action="show_hint", section_id="stale")
    ev.section_id = "sec-live"
    db.add(ev)
    await db.commit()

    r = await client.get(f"{BASE}?hours=24", headers=admin_headers)
    row = [x for x in _rows(r.text) if x["sequence_number"] == "30"][0]
    assert row["section_id"] == "sec-live"


async def test_an_interaction_reaches_the_flat_export(client, db, admin_headers):
    db.add(_ev("adaptation_interaction", cycle=4, seq=40,
               adaptation_id="a9", interaction="dismissed"))
    await db.commit()

    r = await client.get(f"{BASE}?hours=24", headers=admin_headers)
    row = [x for x in _rows(r.text) if x["sequence_number"] == "40"][0]
    assert row["interaction"] == "dismissed"
    assert row["adaptation_id"] == "a9"
