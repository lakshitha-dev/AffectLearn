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

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import structlog

from app.services import redis_service
from app.services.monitor_bus import monitor_bus

logger = structlog.get_logger(__name__)

_STREAM = "research_events"

#: Content-coordinate keys lifted from a resolved section context onto the event envelope
#: (migration 021). `block_id` is absent by design: an affect cycle happens on a SECTION, and
#: only the REST routes acting on a single block (quiz responses) can name a block.
_COORD_KEYS = ("course_id", "section_id")


def content_coords(content_context: dict[str, Any] | None) -> dict[str, Any]:
    """Content coordinates of a cycle, ready to spread onto a research event.

    `content_context_service.build` resolves these while it grounds the prompt, so this is a
    projection of work already done rather than a second lookup on the 30s hot path. Both the
    WebSocket handlers and the agent nodes read the same context, so both stamp identically.

    Returns `{}` when the section is unknown -- an event with no place in the course carries no
    coordinate rather than a row of nulls, which keeps `IS NOT NULL` a meaningful filter.
    """
    if not content_context:
        return {}
    return {key: content_context[key] for key in _COORD_KEYS if content_context.get(key)}

# ── synthetic-run marking ─────────────────────────────────────────────────────────────
#
# `purge_synthetic_events.py` exists because verification traffic injected over the WebSocket is
# INDISTINGUISHABLE from genuine learner cycles in `research_events` -- the table has no origin
# field -- so it entered the research record and showed on the Pipeline Monitor as a learner
# sitting in front of a camera that was never opened. Cleaning it up needed a hand-kept list of
# session ids, which only works if someone wrote the list down.
#
# A run that fabricates cycles marks itself here instead, and every event it produces carries the
# mark. Set at the single emission point for the same reason `config_version` is: there are dozens
# of call sites, and the one that forgot would leave exactly the row an analysis must exclude
# looking exactly like a real one.
#
# The mark lands INSIDE `payload`, not beside it: `research_event_service._row` persists only the
# declared columns and `payload`, so a top-level key would survive the log line and the monitor
# bus and then vanish on the way to the table -- present everywhere it does not matter, absent
# where it does.
_synthetic: ContextVar[bool] = ContextVar("research_synthetic", default=False)


@contextmanager
def synthetic_run():
    """Mark every research event emitted inside this block as fabricated.

    Contextvar-scoped, so it follows the await chain through the whole agent graph without any
    node knowing about it, and it cannot leak into a concurrent real cycle on the same worker.
    """
    token = _synthetic.set(True)
    try:
        yield
    finally:
        _synthetic.reset(token)


def is_synthetic_run() -> bool:
    """Whether the caller is inside a `synthetic_run()` block."""
    return _synthetic.get()


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
        # WHICH CONFIGURATION PRODUCED THIS EVENT.
        #
        # Stamped HERE rather than at each call site, because there are dozens of call sites and
        # one that forgot would leave a hole exactly where an analysis needs to split. The gate's
        # thresholds are editable at runtime, so without this a threshold changed mid-collection
        # would leave no trace and the cycles either side would be pooled as if comparable.
        #
        # A synchronous cache read -- `emit` cannot await, and it must never raise, so a config
        # service that is not yet primed yields the default version rather than failing.
        try:
            from app.services.config_service import get_version

            config_version = get_version()
        except Exception:
            config_version = None

        payload = event.get("payload")
        if _synthetic.get():
            payload = {**(payload if isinstance(payload, dict) else {}), "synthetic": True}

        event = {
            **event,
            "payload": payload,
            "sequence_number": _next_sequence(event.get("session_id")),
            # An explicit value already on the event wins, so a replay or a backfill can state
            # the version the row ORIGINALLY ran under rather than today's.
            "config_version": event.get("config_version", config_version),
        }
        # Live observability fan-out (Redis-independent) before the durable path, so the
        # dashboard sees the event even when Redis is down. Best-effort, never raises.
        monitor_bus.publish({**event, "category": "domain"})
        await redis_service.stream_add(_STREAM, event)  # best-effort durable path
        logger.info("research_event", **event)
    except Exception:
        # Same shape as `trace.emit_trace`: the handler must not be able to raise either, or the
        # "never raises (NFR22)" in the docstring above is not true. A console encoding that
        # cannot represent a character in the event makes `logger.exception` throw exactly where
        # it is being used to swallow a throw.
        try:
            logger.exception("research_event_emit_failed", event_type=event.get("event_type"))
        except Exception:
            pass


def _reset_sequences() -> None:
    """Test helper — clear per-session sequence counters."""
    _sequences.clear()
