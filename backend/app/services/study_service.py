"""Pilot-study logic: A/B group assignment + global study phase (Story 6.1).

Mirrors the decision-logic/IO split of `profile_service.py`: every helper takes a
caller-provided `AsyncSession` (the request/WS `db`), keeps validation in one place, and
`commit()`s after a write. The API routes stay thin (auth → validate → call → shape).

Two research-methodology invariants live here, not in the routes:

1. **Immutability.** `assign_group` updates an UNLOCKED row (pre-pilot correction) but
   raises `GroupAssignmentLockedError` on a LOCKED row — so once `lock_assignments`
   stamps `locked_at` ("pilot begins"), the cohorts can never be silently rewritten and
   cross-contaminated (FR32).
2. **Clean phase boundary.** `set_phase` stamps `transitioned_at` and emits a
   `phase_transition` research event **only on a real change** (`from != to`), so a
   redundant toggle is never logged as a boundary. The Phase A→B timestamp is the cut
   point the dataset is partitioned on for analysis integrity (FR33).

Vocabulary (`GROUPS`/`PHASES`) is imported from `app.agents.state` — the single source of
truth — so it is never redefined here. `get_group` defaults unassigned accounts to
`control` and `get_phase` defaults to `phase_a`, so a missing assignment or a resolution
glitch is always the safe, never-cross-contaminating outcome (never accidentally adaptive).
"""

from __future__ import annotations

import time
import uuid as uuid_mod
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import GROUPS, PHASES
from app.models.study_group import StudyGroup
from app.models.study_phase import StudyPhase
from app.services.research_logger import emit as emit_research_event

DEFAULT_GROUP = "control"
DEFAULT_PHASE = "phase_a"


class GroupAssignmentLockedError(Exception):
    """Raised when re-assigning an account whose group assignment is locked (pilot begun)."""


class InvalidGroupError(ValueError):
    """Raised when a group value is not in GROUPS."""


class InvalidPhaseError(ValueError):
    """Raised when a phase value is not in PHASES."""


def _now_ms() -> int:
    return int(time.time() * 1000)


def _as_uuid(user_id: Any) -> uuid_mod.UUID | None:
    if isinstance(user_id, uuid_mod.UUID):
        return user_id
    try:
        return uuid_mod.UUID(str(user_id))
    except (ValueError, AttributeError, TypeError):
        return None


# ── Group assignment ───────────────────────────────────────────────────────────

async def assign_group(db: AsyncSession, user_id: Any, group: str) -> StudyGroup:
    """Create or correct an account's A/B group assignment.

    Validates `group ∈ GROUPS`. If no row exists, creates one. If a row exists and is
    UNLOCKED, updates it (pre-pilot correction). If it is LOCKED, raises
    `GroupAssignmentLockedError` (immutable once the pilot begins).
    """
    if group not in GROUPS:
        raise InvalidGroupError(f"group must be one of {GROUPS}, got {group!r}")
    uid = _as_uuid(user_id)
    if uid is None:
        raise InvalidGroupError(f"invalid user_id: {user_id!r}")

    row = (
        await db.execute(select(StudyGroup).where(StudyGroup.user_id == uid))
    ).scalar_one_or_none()

    if row is None:
        row = StudyGroup(user_id=uid, group=group)
        db.add(row)
    elif row.locked_at is not None:
        raise GroupAssignmentLockedError(
            f"group assignment for {uid} is locked and cannot be changed"
        )
    else:
        row.group = group

    try:
        await db.commit()
    except IntegrityError:
        # Rare concurrent double-assign: another request inserted a row for this
        # user_id between our SELECT and INSERT (unique constraint on user_id).
        # Roll back and re-fetch the now-existing row to decide what to do.
        await db.rollback()
        row = (
            await db.execute(select(StudyGroup).where(StudyGroup.user_id == uid))
        ).scalar_one_or_none()
        if row is None:
            raise  # unexpected — re-raise
        if row.locked_at is not None:
            raise GroupAssignmentLockedError(
                f"group assignment for {uid} is locked and cannot be changed"
            )
        row.group = group
        await db.commit()

    await db.refresh(row)
    return row


async def get_group(db: AsyncSession, user_id: Any) -> str:
    """Return the account's assigned group, defaulting to `control` when unassigned.

    A learner with no explicit assignment is treated as control — never accidentally
    routed onto the adaptive branch.
    """
    uid = _as_uuid(user_id)
    if uid is None:
        return DEFAULT_GROUP
    row = (
        await db.execute(select(StudyGroup).where(StudyGroup.user_id == uid))
    ).scalar_one_or_none()
    if row is None or row.group not in GROUPS:
        return DEFAULT_GROUP
    return row.group


async def list_assignments(db: AsyncSession) -> list[StudyGroup]:
    """Return all group assignments (newest first)."""
    rows = (
        await db.execute(select(StudyGroup).order_by(StudyGroup.created_at.desc()))
    ).scalars().all()
    return list(rows)


async def lock_assignments(db: AsyncSession) -> int:
    """Stamp `locked_at = now()` on every currently-unlocked row ("pilot begins").

    Returns the count locked. After this, `assign_group` raises on any re-assign.
    """
    now = datetime.now(timezone.utc)
    rows = (
        await db.execute(select(StudyGroup).where(StudyGroup.locked_at.is_(None)))
    ).scalars().all()
    for row in rows:
        row.locked_at = now
    if rows:
        await db.commit()
    return len(rows)


# ── Phase singleton ──────────────────────────────────────────────────────────--

async def _get_phase_row(db: AsyncSession) -> StudyPhase | None:
    """Fetch the single phase row (singleton invariant — created on first set)."""
    return (
        await db.execute(select(StudyPhase).order_by(StudyPhase.created_at.asc()).limit(1))
    ).scalar_one_or_none()


async def get_phase(db: AsyncSession) -> str:
    """Return the current global phase, defaulting to `phase_a` (the pilot starts in A)."""
    row = await _get_phase_row(db)
    if row is None or row.phase not in PHASES:
        return DEFAULT_PHASE
    return row.phase


async def get_phase_state(db: AsyncSession) -> dict[str, Any]:
    """Return `{phase, transitioned_at}` for the GET /admin/study/phase route."""
    row = await _get_phase_row(db)
    if row is None:
        return {"phase": DEFAULT_PHASE, "transitioned_at": None}
    return {"phase": row.phase, "transitioned_at": row.transitioned_at}


async def set_phase(
    db: AsyncSession, phase: str, *, actor_id: Any = None
) -> dict[str, Any]:
    """Set the global phase; stamp `transitioned_at`; emit `phase_transition` on a real change.

    Validates `phase ∈ PHASES`. Returns `{from, to, transitioned_at}`. A no-op set (same
    phase) is allowed but reported as a non-transition (`from == to`) and does NOT emit an
    event — a redundant toggle is not a boundary. On a real change the `phase_transition`
    research event is emitted via the non-blocking `research_logger` (never raises).
    """
    if phase not in PHASES:
        raise InvalidPhaseError(f"phase must be one of {PHASES}, got {phase!r}")

    row = await _get_phase_row(db)
    if row is None:
        previous = DEFAULT_PHASE
        row = StudyPhase(phase=DEFAULT_PHASE)
        db.add(row)
    else:
        previous = row.phase if row.phase in PHASES else DEFAULT_PHASE

    changed = previous != phase
    now = datetime.now(timezone.utc)
    row.phase = phase
    if changed:
        row.transitioned_at = now
    await db.commit()
    await db.refresh(row)

    result = {"from": previous, "to": phase, "transitioned_at": row.transitioned_at}

    if changed:
        # Clean-boundary research event (service-owned, no synchronous DB write in route).
        await emit_research_event({
            "event_type": "phase_transition",
            "learner_id": None,
            "session_id": None,
            "cycle_number": 0,
            "timestamp": _now_ms(),
            # Story 6.5: top-level phase = the NEW phase; group is N/A for a global transition.
            "phase": phase,
            "group": None,
            "payload": {
                "from": previous,
                "to": phase,
                "transitioned_at": row.transitioned_at.isoformat()
                if row.transitioned_at
                else None,
                "actor_id": str(actor_id) if actor_id is not None else None,
            },
        })

    return result
