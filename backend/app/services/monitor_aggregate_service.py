"""Aggregates over `research_events` for the admin monitor's Aggregate tab.

The live SSE stream answers "what is happening right now". This answers "what has the pipeline
actually been doing", which is the question that matters for calibration: at a 0.70 threshold the
gate withholds on the large majority of cycles, and the only way to know whether that is correct
is the DISTRIBUTION OF GATE REASONS. A run that is mostly `low_confidence` is a threshold that is
too high; one that is mostly `cooldown` is a suppression window that is too long.

Read-only. Never writes, never raises on missing data (an empty window returns zeroes).

## Why this scans rather than indexes

`gate_reason` lives in `ResearchEvent.payload`, and that column is generic `sa.JSON` -- NOT
`JSONB` -- so there is no GIN index and no operator class to exploit. Filtering on a payload
field is therefore a scan.

That is acceptable here, deliberately:
  * `event_type` IS indexed, and every query below filters on it first, so the scan is over one
    event type inside a bounded time window, not the whole table.
  * pilot volume is ~120 cycles/learner-hour; a day of 12 sessions is ~1.4k rows.
Revisit (JSONB + GIN, or a generated column) only if a window ever exceeds ~1M rows.

Extraction happens in Python rather than SQL on purpose: `sa.JSON` renders differently across
SQLite (tests) and Postgres (prod), and the row counts here do not justify dialect-specific SQL.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.edges import (
    GATE_COOLDOWN,
    GATE_LOW_CONFIDENCE,
    GATE_NOT_SUSTAINED,
    GATE_STATE_NOT_ACTIONABLE,
)
from app.models.research_event import ResearchEvent
from app.services.analytics_service import _confidence

logger = structlog.get_logger(__name__)

# Every reason the gate can give, so the UI can render a stable set of bars including zeroes.
# Sourced from the GATE_* constants rather than restated, so a new reason cannot be missed here.
GATE_REASONS: tuple[str, ...] = (
    GATE_STATE_NOT_ACTIONABLE,
    GATE_LOW_CONFIDENCE,
    GATE_NOT_SUSTAINED,
    GATE_COOLDOWN,
)

# The event that carries the gate decision (one per completed cycle).
_PROFILE_EVENT = "learner_profile_updated"
_AFFECT_EVENTS = (
    "facial_affect_detected",
    "behavioral_affect_detected",
    "multimodal_affect_detected",
)
_MODALITY_BY_EVENT = {
    "behavioral_affect_detected": "behavioral",
    "facial_affect_detected": "facial",
    "multimodal_affect_detected": "multimodal",
}

_DELIVERED = "adaptation_delivered"
_TRIGGERED = "adaptation_triggered"


def _payload(row: ResearchEvent) -> dict[str, Any]:
    p = row.payload
    return p if isinstance(p, dict) else {}


async def aggregates(db: AsyncSession, *, hours: int = 24) -> dict[str, Any]:
    """Pipeline behaviour over the last `hours`. Safe on an empty table."""
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - hours * 3_600_000

    stmt = select(ResearchEvent).where(ResearchEvent.timestamp >= start_ms)
    rows = list((await db.execute(stmt)).scalars().all())

    events_by_type: dict[str, int] = {}
    sessions: set[str] = set()
    cycles: set[tuple[str, int]] = set()
    gate_counts: dict[str, int] = {r: 0 for r in GATE_REASONS}
    gate_other: dict[str, int] = {}
    affect_counts: dict[str, int] = {}
    delivered = 0
    fallback = 0
    # Per-modality confidence distribution. This exists so the UI can state "this channel never
    # reached the gate in this window" as a MEASUREMENT rather than a hardcoded claim -- and so it
    # stops saying it the moment the channel starts reaching it.
    mod_vals: dict[str, list[float]] = {"behavioral": [], "facial": [], "multimodal": []}

    for r in rows:
        events_by_type[r.event_type] = events_by_type.get(r.event_type, 0) + 1
        if r.session_id:
            sessions.add(r.session_id)
            cycles.add((r.session_id, r.cycle_number or 0))

        pl = _payload(r)

        if r.event_type == _PROFILE_EVENT:
            reason = pl.get("adaptation_gate")
            if isinstance(reason, str):
                if reason in gate_counts:
                    gate_counts[reason] += 1
                else:
                    # A reason the UI does not know about yet -- surface it rather than drop it.
                    gate_other[reason] = gate_other.get(reason, 0) + 1

        elif r.event_type in _AFFECT_EVENTS:
            label = pl.get("affect_state") or pl.get("label")
            if isinstance(label, str):
                affect_counts[label] = affect_counts.get(label, 0) + 1

            modality = _MODALITY_BY_EVENT.get(r.event_type)
            if modality:
                pc = pl.get("p_confused")
                if pc is None:
                    # Older rows predate p_confused being emitted; recover it from the raw
                    # softmax where the head is binary (index 1 == confused).
                    probs = pl.get("probs")
                    if isinstance(probs, list) and len(probs) == 2:
                        pc = probs[1]
                if isinstance(pc, (int, float)):
                    mod_vals[modality].append(float(pc))

        elif r.event_type == _DELIVERED:
            delivered += 1
            if pl.get("fallback") is True:
                fallback += 1

        elif r.event_type == _TRIGGERED and pl.get("fallback") is True:
            # Some fallbacks are recorded on the trigger rather than the delivery.
            fallback += 1

    gated_cycles = sum(gate_counts.values()) + sum(gate_other.values())

    # Compare against the LIVE threshold, so the reported verdict tracks configuration changes.
    try:
        from app.agents.edges import ADAPT_MIN_CONFIDENCE

        threshold = float(ADAPT_MIN_CONFIDENCE)
    except Exception:  # pragma: no cover - defensive
        threshold = None

    modality_stats: dict[str, Any] = {}
    for name, vals in mod_vals.items():
        if not vals:
            modality_stats[name] = {"n": 0}
            continue
        over = sum(1 for v in vals if threshold is not None and v >= threshold)
        modality_stats[name] = {
            "n": len(vals),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
            "mean": round(sum(vals) / len(vals), 4),
            "overThreshold": over,
            # The headline: a channel that never crossed the gate cannot have driven an
            # intervention, no matter what its AUC says.
            "reachedThreshold": over > 0,
        }

    return {
        "windowHours": hours,
        "startTs": start_ms,
        "endTs": now_ms,
        "totalEvents": len(rows),
        "eventsByType": events_by_type,
        "sessions": len(sessions),
        "cycles": len(cycles),
        "interventions": {
            "delivered": delivered,
            # Rate is the number that decides whether the gate is calibrated. ~1.5/hour is the
            # designed operating point at ADAPT_MIN_CONFIDENCE=0.70.
            "perHour": round(delivered / hours, 3) if hours else 0.0,
            "fallback": fallback,
            # Share of delivered adaptations that were canned rather than generated. 1.0 means
            # vLLM is unreachable and every intervention came from the rule-based fallback.
            "fallbackRate": round(fallback / delivered, 3) if delivered else None,
        },
        "gateReasons": gate_counts,
        "gateReasonsUnknown": gate_other,
        "gatedCycles": gated_cycles,
        "affectCounts": affect_counts,
        "modalityStats": modality_stats,
        "adaptMinConfidence": threshold,
        # Reuse the designer analytics confidence rule so "not enough data yet" reads the same
        # way across the product.
        **_confidence(gated_cycles),
    }
