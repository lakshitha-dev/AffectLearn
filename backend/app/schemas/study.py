"""Request/response schemas for the pilot-study admin API (Story 6.1).

`group`/`phase` are typed `Literal` against the locked vocabulary so an out-of-vocabulary
value is rejected at the schema boundary with a 422 (before reaching the service). Response
models use `CamelModel` for the camelCase wire convention (REST default; the WS protocol is
the snake_case exception).
"""

import uuid
from datetime import datetime
from typing import Literal

from app.schemas.base import CamelModel

GroupLiteral = Literal["adaptive", "control"]
PhaseLiteral = Literal["phase_a", "phase_b"]


class GroupAssignRequest(CamelModel):
    user_id: uuid.UUID
    group: GroupLiteral


class GroupAssignmentResponse(CamelModel):
    id: uuid.UUID
    user_id: uuid.UUID
    group: str
    locked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class LockResponse(CamelModel):
    locked_count: int


class PhaseResponse(CamelModel):
    phase: str
    transitioned_at: datetime | None = None


class PhaseSetRequest(CamelModel):
    phase: PhaseLiteral


# PhaseTransitionResponse is returned as a plain dict `{from, to, transitionedAt}` from the
# route: `from`/`to` are Python keywords that can't be model field names, and the keys are
# the research-event contract (`from`/`to`), so the route serializes them directly.


class PhaseTransitionEntry(CamelModel):
    """One recorded move between study phases.

    Reconstructed from the `phase_transition` research events rather than a history table:
    `study_phase` is a singleton holding only the CURRENT phase, so it cannot say when each phase
    began or who began it, while the event log has recorded exactly that all along.
    """

    from_phase: str | None = None
    to_phase: str | None = None
    transitioned_at: str | None = None
    timestamp: int
    actor_id: str | None = None
    #: Resolved for display. None when the account has since been deleted — the transition still
    #: happened, so the row is kept.
    actor_name: str | None = None


class AuditCheck(CamelModel):
    """One research-integrity check (FR50)."""

    id: str
    label: str
    passed: bool
    #: Number of offending rows, so a failure says how bad and not only that it happened.
    count: int
    detail: str
