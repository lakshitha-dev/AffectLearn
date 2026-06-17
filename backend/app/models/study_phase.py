"""Global study-phase singleton store (Story 6.1).

Study phase is ONE system-wide setting, not per-learner: Phase A collects non-adaptive
data for everyone (FR28), Phase B turns the adaptive branch on for Group A only. This
table therefore holds at most a SINGLE row (the singleton invariant): `study_service`
reads/creates the one row by ordered first-fetch and never inserts a second. A dedicated
singleton table (vs a generic key/value `study_settings`) is chosen for auditability —
Open Question 2.

`phase` is one of `app.agents.state.PHASES` (`phase_a` | `phase_b`), defaulting to
`phase_a` (the pilot starts in Phase A). `transitioned_at` stamps the clean Phase A→B
boundary so the research dataset can be partitioned at the exact moment of transition
(data-integrity requirement, FR33). The transition itself emits a `phase_transition`
research event from `study_service.set_phase` on a real change only.
"""

from sqlalchemy import Column, DateTime, String

from app.models.base import BaseModel


class StudyPhase(BaseModel):
    __tablename__ = "study_phase"

    phase = Column(String(16), nullable=False, default="phase_a")
    transitioned_at = Column(DateTime(timezone=True), nullable=True)
