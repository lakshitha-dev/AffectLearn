"""Section progress request/response schemas."""

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.schemas.base import CamelModel

# Upper bound: one section can't legitimately span more than a day of focused time;
# bounding guards the profiler/analytics from corrupt client-supplied values (M1).
_MAX_SECTION_SECONDS = 86_400


class SectionInteractionSignals(CamelModel):
    """Per-section interaction counters the lesson page accumulates, sent on completion.

    These feed the dark-shipped `section_features` research event — candidate confusion signals
    for a detector trained on THIS UI, where the deployed behavioural model is structurally blind
    (4 of its 16 features are scroll-based, but the lesson is one-section-per-page).

    Client-sent rather than derived server-side because `research_logger.emit` goes to a Redis
    stream drained asynchronously into Postgres: a section's events are not queryable when it is
    completed, and are lost outright if Redis is down. The page already holds these counts.

    Every field is optional and bounded — this is best-effort instrumentation, and a client that
    sends nothing (or an old client that does not know the field) must still complete sections
    normally. Bounds keep a buggy or hostile client from writing absurd values into the dataset.
    """

    time_on_section_s: float | None = Field(default=None, ge=0, le=_MAX_SECTION_SECONDS)
    view_count: int | None = Field(default=None, ge=0, le=1000)
    back_nav_count: int | None = Field(default=None, ge=0, le=1000)
    show_answer_used: bool | None = None
    quiz_attempt_count: int | None = Field(default=None, ge=0, le=1000)
    quiz_incorrect_count: int | None = Field(default=None, ge=0, le=1000)
    quiz_response_time_ms_mean: float | None = Field(default=None, ge=0, le=3_600_000)
    exercise_attempt_count: int | None = Field(default=None, ge=0, le=1000)
    adaptation_delivered_count: int | None = Field(default=None, ge=0, le=1000)
    adaptation_dismissed_count: int | None = Field(default=None, ge=0, le=1000)


class SectionProgressCreate(CamelModel):
    section_id: uuid.UUID
    time_spent_seconds: int | None = Field(default=None, ge=0, le=_MAX_SECTION_SECONDS)
    affect_states: list[str] | None = None
    interaction_signals: SectionInteractionSignals | None = None


class SectionProgressResponse(CamelModel):
    id: uuid.UUID
    user_id: uuid.UUID
    section_id: uuid.UUID
    enrollment_id: uuid.UUID
    completed_at: datetime
    time_spent_seconds: int | None = None
    affect_states: list[str] | None = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LessonProgressResponse(CamelModel):
    lesson_id: uuid.UUID
    total_sections: int
    completed_section_ids: list[uuid.UUID]
    lesson_percentage: float


class CourseProgressResponse(CamelModel):
    completed_section_ids: list[uuid.UUID]
    course_percentage: float


class ResumeTargetResponse(CamelModel):
    course_id: uuid.UUID
    module_id: uuid.UUID
    lesson_id: uuid.UUID
    section_id: uuid.UUID
    course_title: str
    module_title: str
    lesson_title: str
    section_title: str
    is_lesson_complete: bool
    is_course_complete: bool
    model_config = ConfigDict(from_attributes=False)
