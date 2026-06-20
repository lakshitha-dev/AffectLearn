"""Post-study satisfaction survey response store (Story 6.4).

One row per **user account** holds the learner's end-of-study satisfaction answers (the four
AC dimensions — perceived adaptation quality, learning experience, willingness to continue,
overall satisfaction) as a `responses` JSON blob. A single structured JSON column is the right
shape (a small, mostly-Likert item set; the research export, Story 6.5, reads it back as
structured JSON rather than one column per question).

`user_id` is unique: re-submitting the survey is an idempotent upsert that updates the caller's
existing row (the submit endpoint operates ONLY on the authenticated user). Mirrors Story 6.3's
`questionnaire_responses` shape exactly (table/class renamed).
"""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import BaseModel


class SurveyResponse(BaseModel):
    __tablename__ = "survey_responses"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    responses = Column(JSON, nullable=False, default=dict)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
