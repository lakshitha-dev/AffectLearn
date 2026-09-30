"""One participant's answers to one administration of a questionnaire (migration 034).

The existing `questionnaire_responses` and `survey_responses` tables hold exactly one row per
account, which fits a single pre-study and a single post-study form and nothing else. The pilot
asks for lesson feedback after EVERY lesson, plus two validated scales at the end, so this table is
one row per administration: which instrument, which version of it, in what context (the lesson it
followed), when it was shown and when it was answered. Skipping is recorded too, with no answers,
because a skipped questionnaire is a different fact from one never shown.

See `services/instruments.py` for the instruments and their validation.
"""

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import BaseModel


class InstrumentResponse(BaseModel):
    __tablename__ = "instrument_responses"

    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    instrument = Column(String(32), nullable=False, index=True)
    instrument_version = Column(String(16), nullable=False)
    #: Where it was administered, e.g. {"course_id": ..., "lesson_id": ...}. Empty for end-of-study.
    context = Column(JSON, nullable=True)
    responses = Column(JSON, nullable=False, default=dict)
    skipped = Column(Boolean, nullable=False, default=False)
    shown_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
