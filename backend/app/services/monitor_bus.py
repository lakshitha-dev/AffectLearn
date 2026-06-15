"""In-process pub/sub event bus for the live observability dashboard (Monitor).

Deliberately Redis-independent: the monitor must work in local/dev where Redis is
down. The bus keeps a bounded ring buffer of recent events (so a freshly-connected
dashboard gets immediate backlog) plus a set of per-subscriber asyncio queues that
SSE connections drain.

Publishing is best-effort and NEVER raises (mirrors research_logger's NFR22 contract):
a slow/full subscriber drops its oldest queued event rather than applying backpressure
to the agent loop.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


class MonitorBus:
    """Fan-out of observability events to a ring buffer + live SSE subscribers."""

    def __init__(self, ring_size: int) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._ring: deque[dict] = deque(maxlen=ring_size)

    def publish(self, event: dict[str, Any]) -> None:
        """Append to the ring buffer and push to every subscriber. Never raises."""
        try:
            self._ring.append(event)
            for q in list(self._subscribers):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    # Drop this subscriber's oldest event to make room — observability
                    # must never slow or block the pipeline.
                    try:
                        q.get_nowait()
                        q.put_nowait(event)
                    except Exception:
                        pass
        except Exception:
            logger.exception("monitor_publish_failed", event_type=event.get("event_type"))

    def subscribe(self, maxsize: int = 1000) -> asyncio.Queue:
        """Register a new subscriber queue (drained by one SSE connection)."""
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def recent(self, session_id: str | None = None, limit: int = 200) -> list[dict]:
        """Return up to `limit` most-recent buffered events, optionally per session."""
        items = list(self._ring)
        if session_id:
            items = [e for e in items if e.get("session_id") == session_id]
        return items[-limit:]

    def session_ids(self) -> list[str]:
        """Distinct session ids seen in the ring buffer (most-recent first)."""
        seen: list[str] = []
        for e in reversed(self._ring):
            sid = e.get("session_id")
            if sid and sid not in seen:
                seen.append(sid)
        return seen

    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def size(self) -> int:
        """Number of events currently held in the ring buffer."""
        return len(self._ring)


monitor_bus = MonitorBus(ring_size=settings.MONITOR_RING_SIZE)
