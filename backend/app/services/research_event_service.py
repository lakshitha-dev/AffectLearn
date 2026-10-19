"""Research event persistence + gap detection (Story 4.7).

Pure-ish DB helpers used by the background worker. `persist_batch` bulk-inserts event
dicts; `detect_gaps` flags missing sequence numbers per session (NFR23). No Redis here.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_event import ResearchEvent

_FIELDS = ("event_id", "decision_id", "event_type", "learner_id", "session_id", "cycle_number",
           "timestamp", "sequence_number", "payload", "phase", "group",
           "course_id", "section_id", "block_id", "config_version")

#: Top-level identity fields persisted as their own columns rather than inside `payload`.
#: All are optional and all are stringified, matching `learner_id` / `session_id`.
_OPTIONAL_STR_FIELDS = ("phase", "group", "course_id", "section_id", "block_id")


def _opt_str(event: dict[str, Any], field: str) -> str | None:
    value = event.get(field)
    return str(value) if value is not None else None


def _row(event: dict[str, Any]) -> ResearchEvent:
    return ResearchEvent(
        # Migration 030: idempotency key assigned at emit. Nullable for rows written before it.
        event_id=(str(event["event_id"]) if event.get("event_id") else None),
        # Migration 031: the graph run this event belongs to, when it belongs to one.
        decision_id=(str(event["decision_id"]) if event.get("decision_id") else None),
        event_type=event.get("event_type", "unknown"),
        learner_id=(str(event["learner_id"]) if event.get("learner_id") is not None else None),
        session_id=(str(event["session_id"]) if event.get("session_id") is not None else None),
        cycle_number=int(event.get("cycle_number", 0) or 0),
        timestamp=int(event.get("timestamp", 0) or 0),
        sequence_number=event.get("sequence_number"),
        payload=event.get("payload"),
        # Migration 027: which runtime configuration produced this row. Nullable, because rows
        # written before the settings feature existed have no answer and must not claim one.
        config_version=(int(event["config_version"])
                        if event.get("config_version") is not None else None),
        # Story 6.5: top-level study phase / A/B group for dataset filtering.
        # Migration 021: content coordinates -- where in the course the event happened.
        # All tolerate absence: connection- and account-level events carry no coordinate.
        **{field: _opt_str(event, field) for field in _OPTIONAL_STR_FIELDS},
    )


async def persist_batch(db: AsyncSession, events: list[dict[str, Any]]) -> int:
    """Insert a batch of event dicts in a single commit, skipping ones already stored.

    Returns the number of rows actually inserted.

    IDEMPOTENT ON `event_id`. The stream hand-off is at-least-once: the worker's cursor is saved
    after the commit, so a crash between the two re-reads a batch that is already in Postgres. An
    event whose `event_id` is already stored -- or repeats earlier in the same batch -- is dropped
    here rather than written twice. Events without an id (emitted before migration 030) cannot be
    matched and are inserted as before.
    """
    if not events:
        return 0
    ids = [str(e["event_id"]) for e in events if e.get("event_id")]
    existing: set[str] = set()
    if ids:
        result = await db.execute(
            select(ResearchEvent.event_id).where(ResearchEvent.event_id.in_(ids))
        )
        existing = {row[0] for row in result.all()}
    rows: list[ResearchEvent] = []
    seen: set[str] = set()
    for event in events:
        event_id = str(event["event_id"]) if event.get("event_id") else None
        if event_id is not None:
            if event_id in existing or event_id in seen:
                continue
            seen.add(event_id)
        rows.append(_row(event))
    if not rows:
        return 0
    db.add_all(rows)
    try:
        await db.commit()
    except IntegrityError:
        # A concurrent writer committed one of these ids between the lookup and the commit
        # (two drain workers). Fall back to row-at-a-time so the rest of the batch still lands.
        await db.rollback()
        inserted = 0
        for event in events:
            event_id = str(event["event_id"]) if event.get("event_id") else None
            if event_id is not None and event_id in existing:
                continue
            db.add(_row(event))
            try:
                await db.commit()
                inserted += 1
            except IntegrityError:
                await db.rollback()
            if event_id is not None:
                existing.add(event_id)
        return inserted
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
