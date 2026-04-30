"""Enrollment request/response schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import ConfigDict

from app.schemas.base import CamelModel, PaginatedResponse


_StatusLiteral = Literal["active", "completed", "dropped"]


class EnrollmentCreate(CamelModel):
    course_id: uuid.UUID


class EnrollmentResponse(CamelModel):
    id: uuid.UUID
    user_id: uuid.UUID
    course_id: uuid.UUID
    enrolled_at: datetime
    progress_percentage: float
    last_accessed_at: datetime | None
    status: _StatusLiteral
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class EnrollmentDetailResponse(EnrollmentResponse):
    """Enrollment with embedded course summary for the My Courses listing."""

    course_title: str
    course_description: str | None = None
    course_estimated_duration_minutes: int | None = None
    course_module_count: int = 0


class EnrollmentListResponse(PaginatedResponse):
    items: list[EnrollmentDetailResponse]
