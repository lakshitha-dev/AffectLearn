"""Tests for hardened research emit (Story 4.7 AC2/AC5)."""

import pytest

from app.services import research_logger


@pytest.fixture(autouse=True)
def _reset():
    research_logger._reset_sequences()
    yield
    research_logger._reset_sequences()


@pytest.mark.asyncio
async def test_emit_assigns_monotonic_sequence_per_session(monkeypatch):
    published: list[dict] = []

    async def fake_stream_add(stream, value):
        published.append(value)
        return "1-0"

    monkeypatch.setattr(research_logger.redis_service, "stream_add", fake_stream_add)

    for _ in range(3):
        await research_logger.emit({"event_type": "affect_classified", "session_id": "s1"})
    await research_logger.emit({"event_type": "affect_classified", "session_id": "s2"})

    s1_seqs = [e["sequence_number"] for e in published if e["session_id"] == "s1"]
    s2_seqs = [e["sequence_number"] for e in published if e["session_id"] == "s2"]
    assert s1_seqs == [1, 2, 3]      # monotonic within session
    assert s2_seqs == [1]            # isolated per session


@pytest.mark.asyncio
async def test_emit_degrades_when_stream_add_raises(monkeypatch):
    async def boom(stream, value):
        raise RuntimeError("redis down")

    monkeypatch.setattr(research_logger.redis_service, "stream_add", boom)
    # Must not raise — structlog backstop (NFR22)
    await research_logger.emit({"event_type": "cycle_completed", "session_id": "s1"})


@pytest.mark.asyncio
async def test_emit_never_raises_on_bad_event(monkeypatch):
    async def ok(stream, value):
        return None

    monkeypatch.setattr(research_logger.redis_service, "stream_add", ok)
    await research_logger.emit({})  # missing everything — still must not raise
