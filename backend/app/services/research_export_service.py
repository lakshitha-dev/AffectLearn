"""Research export/query service (Story 6.5).

Read-only query helpers over `research_events` for the admin export API. Builds filtered,
sequence-ordered `select`s and reuses 4.7's `research_event_service.detect_gaps` for sequence
integrity (NFR23). No writes, no Redis, no file generation (file-download UI is Epic 8 / 8.5).

Ordering invariant: events are returned ordered by `(session_id, sequence_number NULLS LAST,
timestamp)` — i.e. in monotonic per-session sequence order, with a stable timestamp tiebreaker
for rows that have no sequence number. This is the order the Bi-LSTM training assembler and the
gap auditor both rely on.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_event import ResearchEvent
from app.services import demo_scope, research_event_service

# Phase A training-dataset event types: behavioral feature windows + self-report labels.
PHASE_A_EVENT_TYPES = ("behavioral_affect_detected", "self_report")
PHASE_A_PHASE = "phase_a"


def _apply_filters(
    stmt,
    *,
    learner_id: str | None,
    session_id: str | None,
    phase: str | None,
    group: str | None,
    event_types: Sequence[str] | None,
    start_ts: int | None,
    end_ts: int | None,
    course_id: str | None = None,
    section_id: str | None = None,
    exclude_learner_ids: Sequence[str] | None = None,
):
    """Apply the common research-event filters to a select/aggregate statement.

    `exclude_learner_ids` drops the seeded demo accounts (`services/demo_scope.py`): every
    caller here produces research data, and demo rows must never reach it.
    """
    stmt = demo_scope.exclude_learners(stmt, ResearchEvent.learner_id, exclude_learner_ids)
    if learner_id is not None:
        stmt = stmt.where(ResearchEvent.learner_id == learner_id)
    if session_id is not None:
        stmt = stmt.where(ResearchEvent.session_id == session_id)
    # Content coordinates (migration 021). Filtering by section is the point of the column:
    # "every event recorded while learners were on this section" is the query that per-section
    # analytics and the hint-to-outcome join are both built from.
    if course_id is not None:
        stmt = stmt.where(ResearchEvent.course_id == course_id)
    if section_id is not None:
        stmt = stmt.where(ResearchEvent.section_id == section_id)
    if phase is not None:
        stmt = stmt.where(ResearchEvent.phase == phase)
    if group is not None:
        stmt = stmt.where(ResearchEvent.group == group)
    if event_types:
        stmt = stmt.where(ResearchEvent.event_type.in_(list(event_types)))
    if start_ts is not None:
        stmt = stmt.where(ResearchEvent.timestamp >= start_ts)
    if end_ts is not None:
        stmt = stmt.where(ResearchEvent.timestamp <= end_ts)
    return stmt


def _ordered(stmt):
    """Order by (session_id, sequence_number NULLS LAST, timestamp) — sequence order per session."""
    return stmt.order_by(
        ResearchEvent.session_id.asc(),
        ResearchEvent.sequence_number.asc().nullslast(),
        ResearchEvent.timestamp.asc(),
    )


def _to_dict(row: ResearchEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "event_id": row.event_id,
        "decision_id": row.decision_id,
        "event_type": row.event_type,
        "learner_id": row.learner_id,
        "session_id": row.session_id,
        "cycle_number": row.cycle_number,
        "timestamp": row.timestamp,
        "sequence_number": row.sequence_number,
        "phase": row.phase,
        "group": row.group,
        "course_id": row.course_id,
        "section_id": row.section_id,
        "block_id": row.block_id,
        # Which runtime configuration produced the row. Stored since migration 027 but never
        # exported, so an analysis could not split on it without querying the table directly.
        "config_version": row.config_version,
        "payload": row.payload,
    }


async def query_events(
    db: AsyncSession,
    *,
    learner_id: str | None = None,
    session_id: str | None = None,
    phase: str | None = None,
    group: str | None = None,
    event_types: Sequence[str] | None = None,
    start_ts: int | None = None,
    end_ts: int | None = None,
    course_id: str | None = None,
    section_id: str | None = None,
    page: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    """Return a paginated, sequence-ordered page of filtered research events.

    Returns `{items: [dict], total, page, page_size}`. `items` are dicts shaped for
    `ResearchEventOut`. Ordering is `(session_id, sequence_number NULLS LAST, timestamp)`.

    `course_id` / `section_id` filter on the content coordinates added in migration 021. Rows
    written before that migration, and events with no content coordinate (connection- and
    account-level), are excluded by either filter rather than matching null.
    """
    page = max(1, page)
    page_size = max(1, page_size)
    demo_ids = await demo_scope.demo_learner_id_strings(db)

    count_stmt = _apply_filters(
        select(func.count(ResearchEvent.id)),
        learner_id=learner_id, session_id=session_id, phase=phase, group=group,
        event_types=event_types, start_ts=start_ts, end_ts=end_ts,
        course_id=course_id, section_id=section_id, exclude_learner_ids=demo_ids,
    )
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = _apply_filters(
        select(ResearchEvent),
        learner_id=learner_id, session_id=session_id, phase=phase, group=group,
        event_types=event_types, start_ts=start_ts, end_ts=end_ts,
        course_id=course_id, section_id=section_id, exclude_learner_ids=demo_ids,
    )
    stmt = _ordered(stmt).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()

    return {
        "items": [_to_dict(r) for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


async def gaps(
    db: AsyncSession,
    *,
    learner_id: str | None = None,
    session_id: str | None = None,
    phase: str | None = None,
    group: str | None = None,
    event_types: Sequence[str] | None = None,
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> dict[str, list[int]]:
    """Per-session missing sequence numbers (NFR23) for the filtered events.

    Loads ALL matching rows (no pagination — gap detection needs the full sequence span) and
    delegates to `research_event_service.detect_gaps`. Only sessions WITH gaps are returned.
    """
    stmt = _apply_filters(
        select(ResearchEvent),
        learner_id=learner_id, session_id=session_id, phase=phase, group=group,
        event_types=event_types, start_ts=start_ts, end_ts=end_ts,
        exclude_learner_ids=await demo_scope.demo_learner_id_strings(db),
    )
    rows = (await db.execute(_ordered(stmt))).scalars().all()
    return research_event_service.detect_gaps([_to_dict(r) for r in rows])


async def phase_a_dataset(
    db: AsyncSession,
    *,
    learner_id: str | None = None,
    session_id: str | None = None,
    start_ts: int | None = None,
    end_ts: int | None = None,
    page: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    """Phase A training-dataset events: behavioral feature windows + self-report labels.

    Convenience wrapper over `query_events` pinned to `phase="phase_a"` and the behavioral +
    self_report event types, across BOTH groups. The analyst joins behavioral windows to labels
    by `session_id` + nearest preceding `cycle_number`/`timestamp` (documented at the route).
    """
    return await query_events(
        db,
        learner_id=learner_id,
        session_id=session_id,
        phase=PHASE_A_PHASE,
        group=None,
        event_types=PHASE_A_EVENT_TYPES,
        start_ts=start_ts,
        end_ts=end_ts,
        page=page,
        page_size=page_size,
    )
