"""Live-only execution traces for the observability dashboard.

Unlike `research_logger.emit` (durable: Redis Stream -> Postgres), trace events are
EPHEMERAL: they go only to the in-process monitor bus (+ structlog) and are never
persisted, so the research dataset stays free of internal execution spans.

`emit_trace` never raises — tracing must not affect the agent loop.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from app.core.config import settings
from app.services.monitor_bus import monitor_bus

logger = structlog.get_logger(__name__)


def now_ms() -> int:
    return int(time.time() * 1000)


def emit_trace(event_type: str, **fields: Any) -> None:
    """Publish a trace event (category=trace) to the monitor bus. Best-effort."""
    if not settings.MONITOR_ENABLED:
        return
    try:
        event = {
            "category": "trace",
            "event_type": event_type,
            "timestamp": now_ms(),
            **fields,
        }
        monitor_bus.publish(event)
        logger.debug("trace_event", **event)
    except Exception:
        # The handler must not be able to raise either. It did: on a console whose encoding
        # cannot represent a character in the event (a Windows cp1252 stdout and the "→" in the
        # router's reason string), `logger.exception` hit the same UnicodeEncodeError as the
        # `logger.debug` above, and it propagated out of `emit_trace`, out of the instrumented
        # node, and killed the cycle with a 500. The module docstring promises tracing cannot
        # affect the agent loop; without this, it could.
        try:
            logger.exception("emit_trace_failed", event_type=event_type)
        except Exception:
            pass
