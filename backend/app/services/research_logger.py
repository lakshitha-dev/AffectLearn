"""Research event emission — minimal stub for Story 4.1.

Story 4.7 will harden this with a Redis Stream → background worker → PostgreSQL pipeline.
For now: log via structlog (best-effort, non-blocking). Failures must never break the
WebSocket handler or any other caller.
"""

import structlog

logger = structlog.get_logger(__name__)


async def emit(event: dict) -> None:
    """Emit a research event. Best-effort; swallow all exceptions.

    Expected event shape (per architecture spec):
      {
        "event_type": str,        # e.g. "ws_connected"
        "learner_id": str,
        "session_id": str,
        "cycle_number": int,
        "timestamp": int,          # unix ms
        "payload": dict,
      }
    """
    try:
        logger.info("research_event", **event)
    except Exception:
        logger.exception("research_event_emit_failed", event_type=event.get("event_type"))
