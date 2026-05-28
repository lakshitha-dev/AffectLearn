"""Section progress request/response schemas."""

import uuid
from datetime import datetime

from pydantic import ConfigDict

from app.schemas.base import CamelModel


class SectionProgressCreate(CamelModel):
    section_id: uuid.UUID


class SectionProgressResponse(CamelModel):
    id: uuid.UUID
    user_id: uuid.UUID
    section_id: uuid.UUID
    enrollment_id: uuid.UUID
    completed_at: datetime
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
