from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey,
    Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Assessment(BaseModel):
    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint("assessment_type IN ('pre', 'post')", name="ck_assessment_type"),
    )

    module_id = Column(UUID(as_uuid=True), ForeignKey("modules.id", ondelete="CASCADE"), nullable=False, index=True)
    assessment_type = Column(String(10), nullable=False)
    title = Column(String(200), nullable=False)

    questions = relationship("AssessmentQuestion", back_populates="assessment", cascade="all, delete-orphan", order_by="AssessmentQuestion.sort_order")
    attempts = relationship("AssessmentAttempt", back_populates="assessment", cascade="all, delete-orphan")


class AssessmentQuestion(BaseModel):
    __tablename__ = "assessment_questions"
    __table_args__ = (
        UniqueConstraint("assessment_id", "sort_order", name="uq_assessment_question_sort"),
    )

    assessment_id = Column(UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False)
    explanation = Column(Text, nullable=True)

    assessment = relationship("Assessment", back_populates="questions")
    options = relationship("AssessmentOption", back_populates="question", cascade="all, delete-orphan", order_by="AssessmentOption.sort_order")
    responses = relationship("QuestionResponse", back_populates="question", cascade="all, delete-orphan")


class AssessmentOption(BaseModel):
    __tablename__ = "assessment_options"

    question_id = Column(UUID(as_uuid=True), ForeignKey("assessment_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    is_correct = Column(Boolean, nullable=False, default=False)
    sort_order = Column(Integer, nullable=False)

    question = relationship("AssessmentQuestion", back_populates="options")


class AssessmentAttempt(BaseModel):
    __tablename__ = "assessment_attempts"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True)
    score = Column(Integer, nullable=False)
    max_score = Column(Integer, nullable=False)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    #: 1-based, per (user, assessment). Migration 022.
    #:
    #: `api/routes/assessments.py` already reads this when it emits `exercise_attempted` --
    #: int(getattr(result, "attempt_number", 0) or 0) -- but nothing ever set it, so every
    #: research event recorded `attempt: 0`. A pre/post design turns on knowing which attempt a
    #: score belongs to, so a silent constant zero there is a data defect, not a cosmetic one.
    attempt_number = Column(Integer, nullable=False, default=1)
    #: When the learner opened the assessment, so time-taken is derivable. Nullable: attempts
    #: recorded before migration 022 have no start, and a client may not report one.
    started_at = Column(DateTime(timezone=True), nullable=True)

    assessment = relationship("Assessment", back_populates="attempts")
    responses = relationship("QuestionResponse", back_populates="attempt", cascade="all, delete-orphan")


class QuestionResponse(BaseModel):
    __tablename__ = "question_responses"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_question_response"),
    )

    attempt_id = Column(UUID(as_uuid=True), ForeignKey("assessment_attempts.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey("assessment_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    selected_option_id = Column(UUID(as_uuid=True), ForeignKey("assessment_options.id", ondelete="CASCADE"), nullable=False)
    is_correct = Column(Boolean, nullable=False)

    attempt = relationship("AssessmentAttempt", back_populates="responses")
    question = relationship("AssessmentQuestion", back_populates="responses")
