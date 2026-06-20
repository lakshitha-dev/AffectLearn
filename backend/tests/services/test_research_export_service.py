"""Tests for the research export/query service (Story 6.5).

Seeds `ResearchEvent` rows across multiple sessions / phases / groups / event types (incl. a
sequence gap) and asserts: `query_events` orders within a session by sequence and each filter
narrows correctly; `gaps` finds the missing seq; `phase_a_dataset` returns only behavioral +
self_report phase_a rows (both groups).
"""

import pytest

from app.models.research_event import ResearchEvent
from app.services import research_export_service as svc

pytestmark = pytest.mark.asyncio

TS0 = 1_700_000_000_000


async def _seed(db):
    rows = [
        # session s1, phase_a, control: a behavioral window + self_report, seqs 1..4 with a GAP at 3
        ResearchEvent(event_type="behavioral_affect_detected", learner_id="u1", session_id="s1",
                      cycle_number=1, timestamp=TS0 + 1, sequence_number=1, phase="phase_a",
                      group="control", payload={"event_counts": {"keystroke_count": 5}}),
        ResearchEvent(event_type="self_report", learner_id="u1", session_id="s1",
                      cycle_number=1, timestamp=TS0 + 2, sequence_number=2, phase="phase_a",
                      group="control", payload={"affect": "engaged", "skipped": False}),
        # seq 3 deliberately missing -> gap
        ResearchEvent(event_type="section_completed", learner_id="u1", session_id="s1",
                      cycle_number=0, timestamp=TS0 + 4, sequence_number=4, phase="phase_a",
                      group="control", payload={"section_id": "sec-1"}),
        # session s2, phase_b, adaptive: contiguous seqs, behavioral + self_report
        ResearchEvent(event_type="behavioral_affect_detected", learner_id="u2", session_id="s2",
                      cycle_number=1, timestamp=TS0 + 10, sequence_number=1, phase="phase_b",
                      group="adaptive", payload={"event_counts": {}}),
        ResearchEvent(event_type="self_report", learner_id="u2", session_id="s2",
                      cycle_number=1, timestamp=TS0 + 11, sequence_number=2, phase="phase_b",
                      group="adaptive", payload={"affect": "confused", "skipped": False}),
        # session s3, phase_a, adaptive: a behavioral window (other group, still phase A)
        ResearchEvent(event_type="behavioral_affect_detected", learner_id="u3", session_id="s3",
                      cycle_number=1, timestamp=TS0 + 20, sequence_number=1, phase="phase_a",
                      group="adaptive", payload={"event_counts": {}}),
    ]
    db.add_all(rows)
    await db.commit()


async def test_query_events_orders_by_session_then_sequence(db):
    await _seed(db)
    result = await svc.query_events(db)
    items = result["items"]
    assert result["total"] == 6
    # Group by session and assert sequence is monotonic within each.
    by_session: dict[str, list[int]] = {}
    last_session = None
    for it in items:
        by_session.setdefault(it["session_id"], []).append(it["sequence_number"])
        # session ids appear contiguously (ordered by session_id)
        if last_session is not None and it["session_id"] != last_session:
            assert it["session_id"] > last_session
        last_session = it["session_id"]
    assert by_session["s1"] == [1, 2, 4]  # sequence order, gap not back-filled
    assert by_session["s2"] == [1, 2]


async def test_filter_by_phase(db):
    await _seed(db)
    result = await svc.query_events(db, phase="phase_b")
    assert result["total"] == 2
    assert all(it["phase"] == "phase_b" for it in result["items"])


async def test_filter_by_group(db):
    await _seed(db)
    result = await svc.query_events(db, group="adaptive")
    assert result["total"] == 3
    assert all(it["group"] == "adaptive" for it in result["items"])


async def test_filter_by_learner_and_session(db):
    await _seed(db)
    r_learner = await svc.query_events(db, learner_id="u1")
    assert r_learner["total"] == 3
    r_session = await svc.query_events(db, session_id="s2")
    assert r_session["total"] == 2
    assert all(it["session_id"] == "s2" for it in r_session["items"])


async def test_filter_by_event_types(db):
    await _seed(db)
    result = await svc.query_events(
        db, event_types=("self_report", "section_completed")
    )
    assert result["total"] == 3
    assert {it["event_type"] for it in result["items"]} == {
        "self_report", "section_completed"
    }


async def test_filter_by_time_range(db):
    await _seed(db)
    result = await svc.query_events(db, start_ts=TS0 + 10, end_ts=TS0 + 11)
    assert result["total"] == 2
    assert all(TS0 + 10 <= it["timestamp"] <= TS0 + 11 for it in result["items"])


async def test_pagination(db):
    await _seed(db)
    p1 = await svc.query_events(db, page=1, page_size=2)
    p2 = await svc.query_events(db, page=2, page_size=2)
    assert p1["total"] == 6 and p2["total"] == 6
    assert len(p1["items"]) == 2 and len(p2["items"]) == 2
    ids1 = {it["id"] for it in p1["items"]}
    ids2 = {it["id"] for it in p2["items"]}
    assert ids1.isdisjoint(ids2)


async def test_gaps_finds_missing_sequence(db):
    await _seed(db)
    gaps = await svc.gaps(db)
    assert gaps["s1"] == [3]  # 1,2,4 -> missing 3
    assert "s2" not in gaps   # contiguous
    assert "s3" not in gaps   # single event


async def test_phase_a_dataset_returns_behavioral_and_self_report_phase_a_only(db):
    await _seed(db)
    result = await svc.phase_a_dataset(db)
    types = {it["event_type"] for it in result["items"]}
    assert types <= {"behavioral_affect_detected", "self_report"}
    assert all(it["phase"] == "phase_a" for it in result["items"])
    # s1 (control) behavioral + self_report AND s3 (adaptive) behavioral — both groups present.
    groups = {it["group"] for it in result["items"]}
    assert "control" in groups and "adaptive" in groups
    # The phase_b self_report/behavioral rows are excluded.
    assert all(it["session_id"] != "s2" for it in result["items"])
    assert result["total"] == 3
