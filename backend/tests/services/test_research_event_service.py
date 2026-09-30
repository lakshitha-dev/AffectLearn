"""Tests for research event persistence + gap detection (Story 4.7 AC1)."""

import pytest
from sqlalchemy import func, select

from app.models.research_event import ResearchEvent
from app.services import research_event_service as svc

TS0 = 1_700_000_000_000


def _event(seq, session="s1", etype="affect_classified"):
    return {
        "event_type": etype,
        "learner_id": "u1",
        "session_id": session,
        "cycle_number": seq,
        "timestamp": 1_700_000_000_000 + seq,
        "sequence_number": seq,
        "payload": {"affect_state": "engaged"},
    }


@pytest.mark.asyncio
async def test_persist_batch_round_trip(db):
    n = await svc.persist_batch(db, [_event(1), _event(2), _event(3)])
    assert n == 3
    count = (await db.execute(select(func.count(ResearchEvent.id)))).scalar_one()
    assert count == 3
    row = (
        await db.execute(select(ResearchEvent).where(ResearchEvent.sequence_number == 2))
    ).scalar_one()
    assert row.event_type == "affect_classified"
    assert row.payload == {"affect_state": "engaged"}


@pytest.mark.asyncio
async def test_persist_batch_empty_is_noop(db):
    assert await svc.persist_batch(db, []) == 0


def test_detect_gaps_finds_missing_sequences():
    events = [_event(1), _event(2), _event(5), _event(1, session="s2"), _event(2, session="s2")]
    gaps = svc.detect_gaps(events)
    assert gaps["s1"] == [3, 4]   # 1,2,5 -> missing 3,4
    assert "s2" not in gaps        # 1,2 contiguous


def test_detect_gaps_ignores_missing_seq():
    events = [{"session_id": "s1", "sequence_number": None}, {"session_id": "s1"}]
    assert svc.detect_gaps(events) == {}


# ── Story 6.5: top-level phase/group persistence ─────────────────────────────────

@pytest.mark.asyncio
async def test_row_maps_top_level_phase_group():
    row = svc._row({
        "event_type": "self_report",
        "learner_id": "u1",
        "session_id": "s1",
        "cycle_number": 1,
        "timestamp": TS0,
        "sequence_number": 1,
        "phase": "phase_b",
        "group": "adaptive",
        "payload": {"affect": "engaged"},
    })
    assert row.phase == "phase_b"
    assert row.group == "adaptive"


@pytest.mark.asyncio
async def test_row_tolerates_missing_phase_group():
    row = svc._row({"event_type": "x", "session_id": "s1", "timestamp": TS0})
    assert row.phase is None
    assert row.group is None


@pytest.mark.asyncio
async def test_persist_batch_persists_phase_group(db):
    events = [{
        "event_type": "behavioral_affect_detected",
        "learner_id": "u1",
        "session_id": "s1",
        "cycle_number": 1,
        "timestamp": TS0,
        "sequence_number": 1,
        "phase": "phase_a",
        "group": "control",
        "payload": {},
    }]
    assert await svc.persist_batch(db, events) == 1
    row = (
        await db.execute(select(ResearchEvent).where(ResearchEvent.session_id == "s1"))
    ).scalar_one()
    assert row.phase == "phase_a"
    assert row.group == "control"


# ── Migration 021: content coordinates (course_id / section_id / block_id) ───────


@pytest.mark.asyncio
async def test_row_maps_content_coordinates():
    row = svc._row({
        "event_type": "quiz_submitted",
        "learner_id": "u1",
        "session_id": "s1",
        "cycle_number": 1,
        "timestamp": TS0,
        "sequence_number": 1,
        "course_id": "c1",
        "section_id": "sec1",
        "block_id": "blk1",
        "payload": {},
    })
    assert (row.course_id, row.section_id, row.block_id) == ("c1", "sec1", "blk1")


@pytest.mark.asyncio
async def test_row_tolerates_missing_content_coordinates():
    """Connection- and account-level events have no place in the course, and every row written
    before migration 021 predates the columns. Absent must mean NULL, not an error."""
    row = svc._row({"event_type": "ws_connected", "session_id": "s1", "timestamp": TS0})
    assert row.course_id is None
    assert row.section_id is None
    assert row.block_id is None


@pytest.mark.asyncio
async def test_row_stringifies_uuid_coordinates():
    """Emitters pass whatever they hold — a UUID from a route, a str from the agent loop. The
    column is String(64), so the row builder is the single place that normalises."""
    import uuid as uuid_mod

    section = uuid_mod.uuid4()
    row = svc._row({
        "event_type": "section_completed",
        "session_id": "s1",
        "timestamp": TS0,
        "section_id": section,
    })
    assert row.section_id == str(section)


@pytest.mark.asyncio
async def test_persist_batch_persists_content_coordinates(db):
    events = [{
        "event_type": "adaptation_delivered",
        "learner_id": "u1",
        "session_id": "s-coords",
        "cycle_number": 4,
        "timestamp": TS0,
        "sequence_number": 1,
        "course_id": "course-a",
        "section_id": "section-b",
        "payload": {"action": "show_hint"},
    }]
    assert await svc.persist_batch(db, events) == 1
    row = (
        await db.execute(
            select(ResearchEvent).where(ResearchEvent.session_id == "s-coords")
        )
    ).scalar_one()
    assert row.course_id == "course-a"
    assert row.section_id == "section-b"
    assert row.block_id is None


# ── Migration 030: idempotent persistence on event_id ───────────────────────────


def _identified(seq, event_id, session="s1"):
    return {**_event(seq, session=session), "event_id": event_id}


@pytest.mark.asyncio
async def test_persist_batch_skips_event_ids_already_stored(db):
    """A worker restart re-reads a batch it already committed. The re-read must add nothing."""
    batch = [_identified(1, "e-1"), _identified(2, "e-2")]
    assert await svc.persist_batch(db, batch) == 2
    assert await svc.persist_batch(db, batch) == 0
    count = (await db.execute(select(func.count(ResearchEvent.id)))).scalar_one()
    assert count == 2


@pytest.mark.asyncio
async def test_persist_batch_skips_repeats_within_one_batch(db):
    n = await svc.persist_batch(db, [_identified(1, "e-1"), _identified(1, "e-1"),
                                     _identified(2, "e-2")])
    assert n == 2
    ids = (await db.execute(select(ResearchEvent.event_id))).scalars().all()
    assert sorted(ids) == ["e-1", "e-2"]


@pytest.mark.asyncio
async def test_persist_batch_inserts_new_ids_alongside_known_ones(db):
    await svc.persist_batch(db, [_identified(1, "e-1")])
    n = await svc.persist_batch(db, [_identified(1, "e-1"), _identified(2, "e-2")])
    assert n == 1
    count = (await db.execute(select(func.count(ResearchEvent.id)))).scalar_one()
    assert count == 2


@pytest.mark.asyncio
async def test_persist_batch_keeps_events_without_an_id(db):
    """Stream entries emitted before migration 030 carry no id and cannot be matched."""
    assert await svc.persist_batch(db, [_event(1), _event(1)]) == 2
    row = (await db.execute(select(ResearchEvent).limit(1))).scalar_one()
    assert row.event_id is None
