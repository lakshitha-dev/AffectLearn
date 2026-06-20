"""Research event emission (Story 4.1 stub → Story 4.7 durable pipeline).

`emit(event)` is the single emission point, called from `ws.py` (facial/behavioral/
multimodal affect events) and the profiler node (`learner_profile_updated`). The signature
is UNCHANGED, so callers get durability transparently.

Pipeline (Story 4.7): emit assigns a monotonic per-session `sequence_number` (NFR23),
publishes to a Redis Stream (best-effort, non-blocking), and always `structlog`s. The
background worker (`research_worker`) drains the stream into PostgreSQL. Emit NEVER raises
(NFR22) — Redis down degrades to structlog-only and the session/agent loop are unaffected.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.services import redis_service
from app.services.monitor_bus import monitor_bus

logger = structlog.get_logger(__name__)

_STREAM = "research_events"

# Monotonic per-session sequence counters (in-process). One WS connection per learner on
# one server makes this monotonic per session; multi-worker would use Redis INCR (forward).
_sequences: dict[str, int] = {}


def _next_sequence(session_id: Any) -> int:
    key = str(session_id or "")
    nxt = _sequences.get(key, 0) + 1
    _sequences[key] = nxt
    return nxt


async def emit(event: dict[str, Any]) -> None:
    """Emit a research event durably (best-effort). Never raises (NFR22).

    Expected shape: {event_type, learner_id, session_id, cycle_number, timestamp(ms), payload}.
    A monotonic `sequence_number` is added per session for gap detection (NFR23).

    Story 6.5: any top-level `phase`/`group` already on the event are PRESERVED here (the
    `{**event, ...}` spread keeps them at the top level — they must NOT be buried inside
    `payload`), so the worker's `research_event_service._row` persists them as filterable
    columns. The signature is unchanged and emit still never raises.
    """
    try:
        event = {**event, "sequence_number": _next_sequence(event.get("session_id"))}
        # Live observability fan-out (Redis-independent) before the durable path, so the
        # dashboard sees the event even when Redis is down. Best-effort, never raises.
        monitor_bus.publish({**event, "category": "domain"})
        await redis_service.stream_add(_STREAM, event)  # best-effort durable path
        logger.info("research_event", **event)
    except Exception:
        logger.exception("research_event_emit_failed", event_type=event.get("event_type"))


def _reset_sequences() -> None:
    """Test helper — clear per-session sequence counters."""
    _sequences.clear()
