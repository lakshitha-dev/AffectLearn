"""Async CRUD service functions for course enrollments."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course, Module
from app.models.enrollment import Enrollment


async def create_enrollment(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
) -> Enrollment:
    """Enroll a user in a published course.

    Returns the created Enrollment. Raises 404 if course missing/unpublished
    and 409 if the user is already enrolled.
    """
    course = (
        await db.execute(select(Course).where(Course.id == course_id))
    ).scalar_one_or_none()
    if course is None or not course.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Course not found"}},
        )

    enrollment = Enrollment(user_id=user_id, course_id=course_id)
    db.add(enrollment)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "ALREADY_ENROLLED", "message": "Already enrolled in this course"}},
        )
    await db.refresh(enrollment)
    return enrollment


async def get_enrollment(
    db: AsyncSession, *, user_id: uuid.UUID, course_id: uuid.UUID
) -> Enrollment | None:
    """Look up an enrollment by (user, course); return None if not enrolled."""
    stmt = select(Enrollment).where(
        Enrollment.user_id == user_id, Enrollment.course_id == course_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_user_enrollments(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[tuple[Enrollment, Course, int]], int]:
    """Return paginated user enrollments with course summary and module count.

    Sorted by last_accessed_at DESC (NULLs last), then by enrolled_at DESC.
    """
    count_result = await db.execute(
        select(func.count())
        .select_from(Enrollment)
        .where(Enrollment.user_id == user_id)
    )
    total = count_result.scalar_one()

    module_count_subq = (
        select(Module.course_id, func.count(Module.id).label("module_count"))
        .group_by(Module.course_id)
        .subquery()
    )

    stmt = (
        select(
            Enrollment,
            Course,
            func.coalesce(module_count_subq.c.module_count, 0).label("module_count"),
        )
        .join(Course, Enrollment.course_id == Course.id)
        .outerjoin(module_count_subq, module_count_subq.c.course_id == Course.id)
        .where(Enrollment.user_id == user_id)
        .order_by(
            Enrollment.last_accessed_at.desc().nullslast(),
            Enrollment.enrolled_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    rows = [(row[0], row[1], row[2]) for row in result.all()]
    return rows, total


async def update_enrollment_progress(
    db: AsyncSession,
    *,
    enrollment_id: uuid.UUID,
    progress_percentage: float | None = None,
    last_accessed_at: datetime | None = None,
    status_value: Literal["active", "completed", "dropped"] | None = None,
) -> Enrollment:
    """Update enrollment progress; reserved for use by Story 2.4 onwards."""
    result = await db.execute(select(Enrollment).where(Enrollment.id == enrollment_id))
    enrollment = result.scalar_one_or_none()
    if enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Enrollment not found"}},
        )

    if progress_percentage is not None:
        enrollment.progress_percentage = progress_percentage
    if last_accessed_at is not None:
        enrollment.last_accessed_at = last_accessed_at
    if status_value is not None:
        enrollment.status = status_value

    await db.commit()
    await db.refresh(enrollment)
    return enrollment
