"""Background worker: drain the research-event Redis Stream into PostgreSQL (Story 4.7).

`drain_once` reads a batch from the stream and batch-inserts it; `run_worker` loops it,
started best-effort in the app lifespan. Best-effort: if Redis is unavailable the stream
read returns empty and the worker idles/exits — structlog remains the backstop (NFR22).

Durability: the read position (`last_id`) is saved to Redis after every committed batch and
restored on start. It used to live only in memory and start at "0" on every boot, which re-read
and re-inserted the whole stream after each restart. The cursor is saved AFTER the commit, so a
crash in between re-reads at most one batch -- and `persist_batch` skips events whose `event_id`
is already stored, which makes that re-read a no-op. Net effect: at-least-once delivery, exactly
once in the table.
"""

from __future__ import annotations

import asyncio
import time

import structlog

from app.db.session import async_session
from app.services import redis_service, research_event_service

logger = structlog.get_logger(__name__)

_STREAM = "research_events"
_CURSOR_KEY = "research_events:worker_cursor"

# Liveness heartbeat: monotonic time of the worker's last loop iteration (0 = never started).
# Read by the /health/pipeline endpoint so the pilot can detect a stalled drain worker.
_heartbeat: float = 0.0


def heartbeat_age() -> float | None:
    """Seconds since the worker's last loop iteration, or None if it never started."""
    return None if _heartbeat == 0.0 else time.monotonic() - _heartbeat


def is_healthy(max_age_s: float = 15.0) -> bool:
    """True if the worker looped within `max_age_s` (poll interval is ~1s)."""
    age = heartbeat_age()
    return age is not None and age <= max_age_s


async def _drop_erased(events: list[dict]) -> list[dict]:
    """Events of learners erased since they were queued never reach Postgres.

    `data_rights_service.forget_in_redis` marks an erased learner; without this check the worker
    would write their queued events after the erasure had deleted everything else.
    """
    from app.services.data_rights_service import ERASED_KEY

    learners = {str(e["learner_id"]) for e in events if e.get("learner_id")}
    erased = {
        lid for lid in learners
        if await redis_service.exists(ERASED_KEY.format(user_id=lid))
    }
    if not erased:
        return events
    logger.info("research_worker_dropped_erased", learners=len(erased))
    return [e for e in events if str(e.get("learner_id")) not in erased]


async def drain_once(db, last_id: str = "0", count: int = 200) -> tuple[str, int]:
    """Read one batch from the stream and persist it. Returns (advanced_last_id, inserted)."""
    entries = await redis_service.stream_read(_STREAM, count=count, last_id=last_id)
    if not entries:
        return last_id, 0
    events = await _drop_erased([value for _entry_id, value in entries])
    inserted = await research_event_service.persist_batch(db, events)
    return entries[-1][0], inserted


async def load_cursor() -> str | None:
    """The saved read position; "0" (start of the stream) when none is stored.

    None when Redis is unreachable, so the caller retries instead of mistaking an outage for an
    empty cursor and re-reading the whole stream once Redis comes back.
    """
    if not await redis_service.ping():
        return None
    return await redis_service.get_str(_CURSOR_KEY) or "0"


async def save_cursor(last_id: str) -> None:
    await redis_service.set_str(_CURSOR_KEY, last_id)


async def run_worker(stop_event: asyncio.Event | None = None, poll_interval: float = 1.0) -> None:
    """Loop `drain_once` until stopped.

    Runs for the whole app lifetime — it does NOT exit when Redis is unreachable. A transient
    Redis blip only latches `redis_service` off for a short cooldown; the worker keeps polling
    (idle, no-op reads) and resumes draining automatically once Redis recovers, so a single
    timeout can't silently kill research data collection for the rest of the process.
    """
    global _heartbeat
    last_id: str | None = None
    logger.info("research_worker_started")
    while stop_event is None or not stop_event.is_set():
        _heartbeat = time.monotonic()   # liveness beat for /health/pipeline
        try:
            if last_id is None:
                # Resolved inside the loop, not before it: Redis may be down at boot, and a
                # cursor read that failed must be retried rather than defaulting to "0".
                last_id = await load_cursor()
                if last_id is None:
                    await asyncio.sleep(poll_interval)
                    continue
            async with async_session() as db:
                new_last_id, n = await drain_once(db, last_id)
                if new_last_id != last_id:
                    await save_cursor(new_last_id)
                    last_id = new_last_id
                if n:
                    logger.info("research_worker_drained", count=n)
        except Exception:
            logger.exception("research_worker_iteration_failed")
        await asyncio.sleep(poll_interval)
    logger.info("research_worker_stopped")
