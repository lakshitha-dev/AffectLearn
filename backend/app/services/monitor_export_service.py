"""CSV export of `research_events` for the admin monitor.

Nothing in the backend produced CSV before this: `research.py` states plainly that
"CSV/JSON file-download UI is Epic 8 / Story 8.5", and `/data-export` in the frontend shows five
disabled buttons with invented file sizes. Meanwhile three real JSON endpoints existed and had no
consumer. This gives the monitor one honest download.

One row per event, flattened: the columns lift the handful of payload fields that are actually
analysable (affect state, confidence, p_confused, gate reason, model provenance) to the top level
so the file opens usefully in a spreadsheet, while everything else stays in the durable JSON
payload for anyone who needs the full record.

Streamed rather than materialised: a 30-day window at pilot volume is ~40k rows, and there is no
reason to hold that in memory to hand it to a download.
"""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_event import ResearchEvent
from app.services.research_export_service import _apply_filters, _ordered

logger = structlog.get_logger(__name__)

# Column order is the contract for anyone scripting against the download -- append, never reorder.
COLUMNS: tuple[str, ...] = (
    "timestamp",
    "iso_time",
    "session_id",
    "learner_id",
    "cycle_number",
    "sequence_number",
    "event_type",
    "phase",
    "group",
    "affect_state",
    "confidence",
    "p_confused",
    "p_disengaged",
    "model_kind",
    "gate_reason",
    "forced_mode",
    "action",
    "fallback",
)

_BATCH = 500


def _iso(ms: Any) -> str:
    """Millisecond epoch -> ISO-8601 UTC. Blank rather than an exception on a bad value."""
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=UTC).isoformat()
    except Exception:
        return ""


def _row(ev: ResearchEvent) -> list[Any]:
    pl: dict[str, Any] = ev.payload if isinstance(ev.payload, dict) else {}

    # Two binary facial artifacts now write two-element `probs`, and index 1 means a DIFFERENT
    # thing in each: P(confused) for the DAiSEE model, P(disengaged) for the geometry model. The
    # old fallback read probs[1] unconditionally, which filed the geometry channel's disengagement
    # probability under a column headed `p_confused` -- silently mislabelled research data that an
    # analysis would have no way to notice. Each channel now reports into its own column, and the
    # softmax fallback is only applied to the channel it actually belongs to.
    p_conf = pl.get("p_confused")
    p_diseng = pl.get("p_disengaged")
    if p_conf is None and p_diseng is None:
        probs = pl.get("probs")
        if isinstance(probs, list) and len(probs) == 2:
            source = pl.get("affect_source") or ""
            kind = pl.get("model_kind") or ""
            if source == "facial_geometry" or kind == "geometry":
                p_diseng = probs[1]
            elif pl.get("affect_state") == "bored":
                # No provenance on the row (pre-dates affect_source) but the state is one only
                # the geometry channel can produce, so probs[1] is P(disengaged).
                p_diseng = probs[1]
            else:
                p_conf = probs[1]

    return [
        ev.timestamp,
        _iso(ev.timestamp),
        ev.session_id or "",
        ev.learner_id or "",
        ev.cycle_number if ev.cycle_number is not None else "",
        ev.sequence_number if ev.sequence_number is not None else "",
        ev.event_type,
        ev.phase or "",
        # `group` is a reserved SQL word; the ORM attribute is still plain.
        getattr(ev, "group", None) or "",
        pl.get("affect_state") or pl.get("label") or "",
        pl.get("affect_confidence", pl.get("confidence", "")),
        p_conf if p_conf is not None else "",
        p_diseng if p_diseng is not None else "",
        pl.get("model_kind") or "",
        # The gate decision lives on learner_profile_updated as a flat string.
        pl.get("adaptation_gate") or "",
        pl.get("forced_mode") or "",
        pl.get("action") or pl.get("action_type") or "",
        pl.get("fallback") if pl.get("fallback") is not None else "",
    ]


async def stream_csv(
    db: AsyncSession,
    *,
    start_ts: int,
    end_ts: int,
    session_id: str | None = None,
    event_types: Sequence[str] | None = None,
) -> AsyncIterator[str]:
    """Yield CSV text, header first, in batches.

    Ordering reuses `research_export_service._ordered` so the download matches the export API's
    invariant -- `(session_id, sequence_number NULLS LAST, timestamp)` -- which is the order the
    gap auditor and the training assembler both rely on. Do not sort differently here.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")

    def flush() -> str:
        out = buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        return out

    writer.writerow(COLUMNS)
    yield flush()

    stmt = _apply_filters(
        select(ResearchEvent),
        learner_id=None,
        session_id=session_id,
        phase=None,
        group=None,
        event_types=event_types,
        start_ts=start_ts,
        end_ts=end_ts,
    )
    result = await db.stream(_ordered(stmt))

    n = 0
    async for row in result.scalars():
        writer.writerow(_row(row))
        n += 1
        if n % _BATCH == 0:
            yield flush()
    tail = flush()
    if tail:
        yield tail
    logger.info("monitor_csv_exported", rows=n, session_id=session_id)
