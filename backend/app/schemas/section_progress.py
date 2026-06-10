"""Section progress request/response schemas."""

import uuid
from datetime import datetime

from pydantic import ConfigDict, Field

from app.schemas.base import CamelModel

# Upper bound: one section can't legitimately span more than a day of focused time;
# bounding guards the profiler/analytics from corrupt client-supplied values (M1).
_MAX_SECTION_SECONDS = 86_400


class SectionProgressCreate(CamelModel):
    section_id: uuid.UUID
    time_spent_seconds: int | None = Field(default=None, ge=0, le=_MAX_SECTION_SECONDS)
    affect_states: list[str] | None = None


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
