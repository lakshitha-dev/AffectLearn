"""Async service functions for learner section-progress tracking."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.course import Course, Lesson, Module, Section
from app.models.enrollment import Enrollment
from app.models.section_progress import SectionProgress


async def _get_section_with_hierarchy(
    db: AsyncSession, section_id: uuid.UUID
) -> Section | None:
    stmt = (
        select(Section)
        .where(Section.id == section_id)
        .options(selectinload(Section.lesson).selectinload(Lesson.module))
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _recompute_enrollment_progress(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    enrollment: Enrollment,
) -> None:
    """Recompute enrollment.progress_percentage via single SQL aggregate.

    Counts total sections in the course (joined through modules + lessons) and
    completed section_progress rows for this user constrained to those
    sections; computes percentage server-side.
    """
    total_stmt = (
        select(func.count(Section.id))
        .select_from(Section)
        .join(Lesson, Section.lesson_id == Lesson.id)
        .join(Module, Lesson.module_id == Module.id)
        .where(Module.course_id == course_id)
    )
    total_sections = (await db.execute(total_stmt)).scalar_one()

    completed_stmt = (
        select(func.count(SectionProgress.id))
        .select_from(SectionProgress)
        .join(Section, SectionProgress.section_id == Section.id)
        .join(Lesson, Section.lesson_id == Lesson.id)
        .join(Module, Lesson.module_id == Module.id)
        .where(
            SectionProgress.user_id == user_id,
            Module.course_id == course_id,
        )
    )
    completed_sections = (await db.execute(completed_stmt)).scalar_one()

    if total_sections > 0:
        enrollment.progress_percentage = (completed_sections * 100.0) / total_sections
    else:
        enrollment.progress_percentage = 0.0
    enrollment.last_accessed_at = func.now()


async def mark_section_complete(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    section_id: uuid.UUID,
) -> tuple[SectionProgress, bool]:
    """Idempotently record a section as completed by a user.

    Returns (record, created) where `created` is True if a new row was
    inserted, False if the user had already completed this section. Raises
    404 if the section does not exist and 403 if the user is not enrolled in
    the parent course.
    """
    section = await _get_section_with_hierarchy(db, section_id)
    if section is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Section not found"}},
        )

    course_id = section.lesson.module.course_id

    enrollment_stmt = select(Enrollment).where(
        Enrollment.user_id == user_id,
        Enrollment.course_id == course_id,
    )
    enrollment = (await db.execute(enrollment_stmt)).scalar_one_or_none()
    if enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "NOT_ENROLLED",
                    "message": "You must enroll in this course before tracking progress",
                }
            },
        )

    existing_stmt = select(SectionProgress).where(
        SectionProgress.user_id == user_id,
        SectionProgress.section_id == section_id,
    )
    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing is not None:
        # Already complete: refresh last_accessed_at then return idempotently.
        enrollment.last_accessed_at = func.now()
        await db.commit()
        await db.refresh(existing)
        return existing, False

    progress = SectionProgress(
        user_id=user_id,
        section_id=section_id,
        enrollment_id=enrollment.id,
    )
    db.add(progress)
    try:
        await db.flush()
    except IntegrityError:
        # Race: another request inserted between our SELECT and INSERT.
        await db.rollback()
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing is None:
            raise
        enrollment_refresh = (await db.execute(enrollment_stmt)).scalar_one()
        enrollment_refresh.last_accessed_at = func.now()
        await db.commit()
        await db.refresh(existing)
        return existing, False

    await _recompute_enrollment_progress(
        db, user_id=user_id, course_id=course_id, enrollment=enrollment
    )
    await db.commit()
    await db.refresh(progress)
    return progress, True


async def get_lesson_progress(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    lesson_id: uuid.UUID,
) -> dict:
    """Return total + completed section counts for a lesson."""
    lesson_stmt = select(Lesson).where(Lesson.id == lesson_id)
    lesson = (await db.execute(lesson_stmt)).scalar_one_or_none()
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Lesson not found"}},
        )

    section_ids_stmt = select(Section.id).where(Section.lesson_id == lesson_id)
    section_ids = list((await db.execute(section_ids_stmt)).scalars().all())
    total_sections = len(section_ids)

    completed_section_ids: list[uuid.UUID] = []
    if total_sections > 0:
        completed_stmt = select(SectionProgress.section_id).where(
            SectionProgress.user_id == user_id,
            SectionProgress.section_id.in_(section_ids),
        )
        completed_section_ids = list(
            (await db.execute(completed_stmt)).scalars().all()
        )

    lesson_percentage = (
        (len(completed_section_ids) * 100.0) / total_sections
        if total_sections > 0
        else 0.0
    )

    return {
        "lesson_id": lesson_id,
        "total_sections": total_sections,
        "completed_section_ids": completed_section_ids,
        "lesson_percentage": lesson_percentage,
    }


async def compute_resume_target(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
) -> dict:
    """Return the resume target (first incomplete section) for a learner in a course.

    Uses a single LEFT JOIN query ordered by sort_order. Returns a domain dict
    that the route layer maps to ResumeTargetResponse.
    """
    enrollment = await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == user_id,
            Enrollment.course_id == course_id,
        )
    )
    if enrollment.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_ENROLLED", "message": "Not enrolled in this course"}},
        )

    stmt = (
        select(
            Section.id.label("section_id"),
            Section.title.label("section_title"),
            Section.sort_order.label("section_sort"),
            Lesson.id.label("lesson_id"),
            Lesson.title.label("lesson_title"),
            Lesson.sort_order.label("lesson_sort"),
            Module.id.label("module_id"),
            Module.title.label("module_title"),
            Module.sort_order.label("module_sort"),
            Course.title.label("course_title"),
            SectionProgress.id.label("progress_id"),
        )
        .select_from(Section)
        .join(Lesson, Section.lesson_id == Lesson.id)
        .join(Module, Lesson.module_id == Module.id)
        .join(Course, Module.course_id == Course.id)
        .outerjoin(
            SectionProgress,
            (SectionProgress.section_id == Section.id)
            & (SectionProgress.user_id == user_id),
        )
        .where(Module.course_id == course_id)
        .order_by(Module.sort_order, Lesson.sort_order, Section.sort_order)
    )
    rows = (await db.execute(stmt)).all()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "COURSE_EMPTY", "message": "Course has no content yet"}},
        )

    target_row = next((r for r in rows if r.progress_id is None), rows[-1])
    is_course_complete = all(r.progress_id is not None for r in rows)
    is_lesson_complete = all(
        r.progress_id is not None
        for r in rows
        if r.lesson_id == target_row.lesson_id
    )

    return {
        "course_id": course_id,
        "module_id": target_row.module_id,
        "lesson_id": target_row.lesson_id,
        "section_id": target_row.section_id,
        "course_title": target_row.course_title,
        "module_title": target_row.module_title,
        "lesson_title": target_row.lesson_title,
        "section_title": target_row.section_title,
        "is_lesson_complete": is_lesson_complete,
        "is_course_complete": is_course_complete,
    }


async def get_course_progress(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
) -> dict:
    """Return all completed section IDs for a user in a course."""
    course_exists = (
        await db.execute(select(Course.id).where(Course.id == course_id))
    ).scalar_one_or_none()
    if course_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Course not found"}},
        )

    total_stmt = (
        select(func.count(Section.id))
        .select_from(Section)
        .join(Lesson, Section.lesson_id == Lesson.id)
        .join(Module, Lesson.module_id == Module.id)
        .where(Module.course_id == course_id)
    )
    total_sections = (await db.execute(total_stmt)).scalar_one()

    completed_stmt = (
        select(SectionProgress.section_id)
        .select_from(SectionProgress)
        .join(Section, SectionProgress.section_id == Section.id)
        .join(Lesson, Section.lesson_id == Lesson.id)
        .join(Module, Lesson.module_id == Module.id)
        .where(
            SectionProgress.user_id == user_id,
            Module.course_id == course_id,
        )
    )
    completed_section_ids = list(
        (await db.execute(completed_stmt)).scalars().all()
    )

    course_percentage = (
        (len(completed_section_ids) * 100.0) / total_sections
        if total_sections > 0
        else 0.0
    )

    return {
        "completed_section_ids": completed_section_ids,
        "course_percentage": course_percentage,
    }
