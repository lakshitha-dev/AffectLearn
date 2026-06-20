"""Pre-study questionnaire response store (Story 6.3).

One row per **user account** holds the learner's baseline questionnaire answers (the
instrument's Sections A–E, Q1–Q14) as a heterogeneous `responses` JSON blob. The 15
items are heterogeneous (single-select, multi-select, 5-point Likert, a Likert matrix),
so a single structured JSON column is the right shape — the research export (Story 6.5)
reads it back as structured JSON rather than reconstructing 14 typed columns.

`user_id` is unique: re-submitting the questionnaire is an idempotent upsert that updates
the caller's existing row (the submit endpoint operates ONLY on the authenticated user).
Consent (the instrument's Section F / Q15) is intentionally NOT collected here — Epic 3's
`ConsentStep` already persists informed consent (`011_add_consent_to_users`).
"""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import BaseModel


class QuestionnaireResponse(BaseModel):
    __tablename__ = "questionnaire_responses"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    responses = Column(JSON, nullable=False, default=dict)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
