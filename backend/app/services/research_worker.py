"""Background worker: drain the research-event Redis Stream into PostgreSQL (Story 4.7).

`drain_once` reads a batch from the stream and batch-inserts it; `run_worker` loops it,
started best-effort in the app lifespan. Best-effort: if Redis is unavailable the stream
read returns empty and the worker idles/exits — structlog remains the backstop (NFR22).

Durability note: this uses a simple XREAD with a tracked `last_id` (single worker). At-least-
once across worker restarts (XREADGROUP + XACK) is a documented upgrade; duplicates from a
restart are de-dupable offline by (session_id, sequence_number).
"""

from __future__ import annotations

import asyncio

import structlog

from app.db.session import async_session
from app.services import redis_service, research_event_service

logger = structlog.get_logger(__name__)

_STREAM = "research_events"


async def drain_once(db, last_id: str = "0", count: int = 200) -> tuple[str, int]:
    """Read one batch from the stream and persist it. Returns (advanced_last_id, inserted)."""
    entries = await redis_service.stream_read(_STREAM, count=count, last_id=last_id)
    if not entries:
        return last_id, 0
    events = [value for _entry_id, value in entries]
    inserted = await research_event_service.persist_batch(db, events)
    return entries[-1][0], inserted


async def run_worker(stop_event: asyncio.Event | None = None, poll_interval: float = 1.0) -> None:
    """Loop `drain_once` until stopped.

    Runs for the whole app lifetime — it does NOT exit when Redis is unreachable. A transient
    Redis blip only latches `redis_service` off for a short cooldown; the worker keeps polling
    (idle, no-op reads) and resumes draining automatically once Redis recovers, so a single
    timeout can't silently kill research data collection for the rest of the process.
    """
    last_id = "0"
    logger.info("research_worker_started")
    while stop_event is None or not stop_event.is_set():
        try:
            async with async_session() as db:
                last_id, n = await drain_once(db, last_id)
                if n:
                    logger.info("research_worker_drained", count=n)
        except Exception:
            logger.exception("research_worker_iteration_failed")
        await asyncio.sleep(poll_interval)
    logger.info("research_worker_stopped")
