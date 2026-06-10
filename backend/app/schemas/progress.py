"""Learner progress aggregation response schemas (Story 4.6)."""

import uuid
from datetime import datetime

from app.schemas.base import CamelModel


class CourseProgressEntry(CamelModel):
    course_id: uuid.UUID
    course_title: str
    total_sections: int
    completed_sections: int
    percentage: float


class SectionProgressEntry(CamelModel):
    section_id: uuid.UUID
    completed_at: datetime
    time_spent_seconds: int | None = None
    affect_states: list[str] | None = None


class QuizTally(CamelModel):
    answered: int
    correct: int


class LearnerProgressResponse(CamelModel):
    courses: list[CourseProgressEntry]
    sections: list[SectionProgressEntry]
    quizzes: QuizTally
