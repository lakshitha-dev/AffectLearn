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


def test_heartbeat_reports_liveness(monkeypatch):
    import time
    # Never started -> no heartbeat -> not healthy.
    monkeypatch.setattr(research_worker, "_heartbeat", 0.0, raising=False)
    assert research_worker.heartbeat_age() is None
    assert research_worker.is_healthy() is False
    # Fresh beat -> healthy; stale beat -> unhealthy.
    monkeypatch.setattr(research_worker, "_heartbeat", time.monotonic(), raising=False)
    assert research_worker.is_healthy(max_age_s=15) is True
    monkeypatch.setattr(research_worker, "_heartbeat", time.monotonic() - 60, raising=False)
    assert research_worker.is_healthy(max_age_s=15) is False


# ── cursor persistence: a restart must not re-read the stream from "0" ─────────


@pytest.mark.asyncio
async def test_worker_resumes_from_saved_cursor_and_saves_progress(monkeypatch):
    import asyncio

    store: dict[str, str] = {"research_events:worker_cursor": "7-0"}
    reads: list[str] = []
    stop = asyncio.Event()

    async def fake_ping():
        return True

    async def fake_get_str(key):
        return store.get(key)

    async def fake_set_str(key, value, ttl_seconds=None):
        store[key] = value
        return True

    async def fake_drain_once(db, last_id="0", count=200):
        reads.append(last_id)
        stop.set()
        return "9-0", 2

    class _Session:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(research_worker.redis_service, "ping", fake_ping)
    monkeypatch.setattr(research_worker.redis_service, "get_str", fake_get_str)
    monkeypatch.setattr(research_worker.redis_service, "set_str", fake_set_str)
    monkeypatch.setattr(research_worker, "drain_once", fake_drain_once)
    monkeypatch.setattr(research_worker, "async_session", lambda: _Session())

    await research_worker.run_worker(stop_event=stop, poll_interval=0)

    assert reads == ["7-0"]                                   # resumed, not "0"
    assert store["research_events:worker_cursor"] == "9-0"    # progress saved


@pytest.mark.asyncio
async def test_load_cursor_defaults_to_start_only_when_redis_answers(monkeypatch):
    async def up():
        return True

    async def down():
        return False

    async def nothing(key):
        return None

    monkeypatch.setattr(research_worker.redis_service, "get_str", nothing)
    monkeypatch.setattr(research_worker.redis_service, "ping", up)
    assert await research_worker.load_cursor() == "0"
    # An outage is not an empty cursor: the worker must retry, not restart from "0".
    monkeypatch.setattr(research_worker.redis_service, "ping", down)
    assert await research_worker.load_cursor() is None
