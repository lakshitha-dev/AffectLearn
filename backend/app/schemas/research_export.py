"""Research export/query API response schemas (Story 6.5).

camelCase (`CamelModel`) response shapes for the admin research export API. Every event row
carries the full 4.7+6.5 envelope (event_type, learner_id, session_id, cycle_number, timestamp,
sequence_number, phase, group), the migration-021 content coordinates (course_id, section_id,
block_id) and the JSON payload. These are read-only projections of
`ResearchEvent`; no file generation here (CSV/JSON file-download UI is Epic 8 / Story 8.5).
"""

from __future__ import annotations

from typing import Any

from app.schemas.base import CamelModel


class ResearchEventOut(CamelModel):
    """One persisted research event, full envelope + payload (camelCase on the wire)."""

    id: str
    # Idempotency key assigned at emit (migration 030). Null on rows written before it.
    event_id: str | None = None
    # The graph run this event belongs to (migration 031). Null outside a run.
    decision_id: str | None = None
    event_type: str
    learner_id: str | None = None
    session_id: str | None = None
    cycle_number: int
    timestamp: int  # unix ms
    sequence_number: int | None = None
    phase: str | None = None
    group: str | None = None
    # Content coordinates (migration 021). Null on connection- and account-level events, which
    # have no place in the course, and on every row written before the migration.
    course_id: str | None = None
    section_id: str | None = None
    block_id: str | None = None
    config_version: int | None = None
    payload: dict[str, Any] | None = None


class ResearchEventPage(CamelModel):
    """Paginated events page (ordered by session_id, then sequence_number, then timestamp)."""

    items: list[ResearchEventOut]
    total: int
    page: int
    page_size: int


class SequenceGapsOut(CamelModel):
    """Per-session missing sequence numbers (NFR23). Only sessions WITH gaps are included."""

    gaps: dict[str, list[int]]
