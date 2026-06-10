"""Tests for research event persistence + gap detection (Story 4.7 AC1)."""

import pytest
from sqlalchemy import func, select

from app.models.research_event import ResearchEvent
from app.services import research_event_service as svc


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
