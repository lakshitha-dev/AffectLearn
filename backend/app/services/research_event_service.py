"""Research event persistence + gap detection (Story 4.7).

Pure-ish DB helpers used by the background worker. `persist_batch` bulk-inserts event
dicts; `detect_gaps` flags missing sequence numbers per session (NFR23). No Redis here.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_event import ResearchEvent

_FIELDS = ("event_type", "learner_id", "session_id", "cycle_number",
           "timestamp", "sequence_number", "payload")


def _row(event: dict[str, Any]) -> ResearchEvent:
    return ResearchEvent(
        event_type=event.get("event_type", "unknown"),
        learner_id=(str(event["learner_id"]) if event.get("learner_id") is not None else None),
        session_id=(str(event["session_id"]) if event.get("session_id") is not None else None),
        cycle_number=int(event.get("cycle_number", 0) or 0),
        timestamp=int(event.get("timestamp", 0) or 0),
        sequence_number=event.get("sequence_number"),
        payload=event.get("payload"),
    )


async def persist_batch(db: AsyncSession, events: list[dict[str, Any]]) -> int:
    """Bulk-insert a batch of event dicts in a single commit. Returns count inserted."""
    if not events:
        return 0
    rows = [_row(e) for e in events]
    db.add_all(rows)
    await db.commit()
    return len(rows)


def detect_gaps(events: list[dict[str, Any]]) -> dict[str, list[int]]:
    """Per session, the missing sequence numbers between the min and max observed.

    Events with no `sequence_number` are ignored. A session with a contiguous run has no
    gaps. Used for NFR23 integrity checks on the persisted dataset.
    """
    by_session: dict[str, set[int]] = defaultdict(set)
    for e in events:
        seq = e.get("sequence_number")
        if seq is None:
            continue
        by_session[str(e.get("session_id"))].add(int(seq))

    gaps: dict[str, list[int]] = {}
    for session, seqs in by_session.items():
        lo, hi = min(seqs), max(seqs)
        missing = [n for n in range(lo, hi + 1) if n not in seqs]
        if missing:
            gaps[session] = missing
    return gaps
