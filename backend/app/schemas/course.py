"""Course content request/response schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field

from app.schemas.base import CamelModel, PaginatedResponse


# ---------------------------------------------------------------------------
# ContentBlock schemas
# ---------------------------------------------------------------------------

_BlockTypeLiteral = Literal["text", "code", "image", "callout", "exercise", "quiz"]


class ContentBlockCreate(CamelModel):
    block_type: _BlockTypeLiteral
    content: dict
    sort_order: int = Field(ge=0)
    variant_key: str = Field(default="original", max_length=50)
    variant_group: uuid.UUID | None = None


class ContentBlockUpdate(CamelModel):
    block_type: _BlockTypeLiteral | None = None
    content: dict | None = None
    sort_order: int | None = Field(default=None, ge=0)
    variant_key: str | None = Field(default=None, max_length=50)


class ContentBlockResponse(CamelModel):
    id: uuid.UUID
    block_type: str
    content: dict
    sort_order: int
    variant_key: str
    variant_group: uuid.UUID
    section_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Section schemas
# ---------------------------------------------------------------------------

class SectionCreate(CamelModel):
    title: str = Field(min_length=1, max_length=200)
    sort_order: int = Field(ge=0)
    estimated_duration_minutes: int | None = Field(default=5, ge=0)


class SectionUpdate(CamelModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = Field(default=None, ge=0)
    estimated_duration_minutes: int | None = Field(default=None, ge=0)


class SectionResponse(CamelModel):
    id: uuid.UUID
    title: str
    sort_order: int
    estimated_duration_minutes: int | None
    lesson_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SectionDetailResponse(SectionResponse):
    content_blocks: list[ContentBlockResponse] = []


# ---------------------------------------------------------------------------
# Lesson schemas
# ---------------------------------------------------------------------------

class LessonCreate(CamelModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    sort_order: int = Field(ge=0)


class LessonUpdate(CamelModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    sort_order: int | None = Field(default=None, ge=0)


class LessonResponse(CamelModel):
    id: uuid.UUID
    title: str
    description: str | None
    sort_order: int
    module_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LessonDetailResponse(LessonResponse):
    sections: list[SectionDetailResponse] = []


# ---------------------------------------------------------------------------
# Module schemas
# ---------------------------------------------------------------------------

class ModuleCreate(CamelModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    sort_order: int = Field(ge=0)


class ModuleUpdate(CamelModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    sort_order: int | None = Field(default=None, ge=0)


class ModuleResponse(CamelModel):
    id: uuid.UUID
    title: str
    description: str | None
    sort_order: int
    course_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ModuleDetailResponse(ModuleResponse):
    lessons: list[LessonDetailResponse] = []


# ---------------------------------------------------------------------------
# Course schemas
# ---------------------------------------------------------------------------

class CourseCreate(CamelModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    estimated_duration_minutes: int | None = Field(default=None, ge=0)
    is_published: bool = False
    learning_objectives: str | None = None


class CourseUpdate(CamelModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    estimated_duration_minutes: int | None = Field(default=None, ge=0)
    is_published: bool | None = None
    learning_objectives: str | None = None


class CourseResponse(CamelModel):
    id: uuid.UUID
    title: str
    description: str | None
    estimated_duration_minutes: int | None
    is_published: bool
    learning_objectives: str | None = None
    created_at: datetime
    updated_at: datetime
    # Annotations populated when the requesting user is an authenticated learner.
    is_enrolled: bool | None = None
    enrollment_progress: float | None = None
    module_count: int | None = None
    # Ownership (migration 024). `created_by` is null for seeded system content.
    created_by: uuid.UUID | None = None
    # Whether the REQUESTING user may modify this course. Computed server-side from the same
    # predicate the write guards use, so the authoring UI can hide actions the API would refuse
    # instead of re-deriving the rule in TypeScript and letting the two drift.
    can_edit: bool | None = None
    model_config = ConfigDict(from_attributes=True)


class CourseDetailResponse(CourseResponse):
    modules: list[ModuleDetailResponse] = []


class CourseListResponse(PaginatedResponse):
    items: list[CourseResponse]
