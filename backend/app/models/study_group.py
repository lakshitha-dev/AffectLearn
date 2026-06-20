"""A/B study-group assignment store (Story 6.1).

One immutable row per **user account** (not per device) records the learner's pilot
cohort: `adaptive` (Phase B receives adaptations) or `control` (always log-only). The
assignment is tied to `user_id` (unique) so a learner on two devices is the SAME group —
there is no per-device drift that could cross-contaminate the control vs adaptive cohorts.

Immutability: `locked_at` is NULL pre-pilot (the coordinator may correct an assignment),
and is stamped when the pilot begins (`study_service.lock_assignments`). Once locked, the
service raises `GroupAssignmentLockedError` on any re-assign so the cohorts can never be
silently rewritten mid-study — this is the keystone research-integrity guarantee (FR32).

`group` is validated against `app.agents.state.GROUPS` in the service (single source of
truth); the column itself is a plain String to avoid duplicating the vocabulary here.
"""

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import BaseModel


class StudyGroup(BaseModel):
    __tablename__ = "study_groups"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    group = Column(String(16), nullable=False)
    locked_at = Column(DateTime(timezone=True), nullable=True)
