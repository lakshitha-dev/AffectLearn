"""Tests for the research-event worker drain (Story 4.7 AC4)."""

import pytest
from sqlalchemy import func, select

from app.models.research_event import ResearchEvent
from app.services import research_worker


@pytest.mark.asyncio
async def test_drain_once_persists_and_advances(monkeypatch, db):
    fake_entries = [
        ("1-0", {"event_type": "affect_classified", "session_id": "s1",
                 "cycle_number": 1, "timestamp": 1, "sequence_number": 1, "payload": {}}),
        ("2-0", {"event_type": "learner_profile_updated", "session_id": "s1",
                 "cycle_number": 1, "timestamp": 2, "sequence_number": 2, "payload": {}}),
    ]

    async def fake_stream_read(stream, count=100, last_id="0"):
        return fake_entries

    monkeypatch.setattr(research_worker.redis_service, "stream_read", fake_stream_read)

    new_last_id, count = await research_worker.drain_once(db, last_id="0")
    assert count == 2
    assert new_last_id == "2-0"          # advanced to the last entry id

    persisted = (await db.execute(select(func.count(ResearchEvent.id)))).scalar_one()
    assert persisted == 2


@pytest.mark.asyncio
async def test_drain_once_empty_stream_is_noop(monkeypatch, db):
    async def empty(stream, count=100, last_id="0"):
        return []

    monkeypatch.setattr(research_worker.redis_service, "stream_read", empty)
    new_last_id, count = await research_worker.drain_once(db, last_id="5-0")
    assert count == 0
    assert new_last_id == "5-0"          # unchanged when nothing to read
