"""Who may edit a course, and everything inside it (migration 024).

WHY THIS IS SEPARATE FROM `require_role`

`require_role(course_designer, admin)` answers "is this person a designer?" It has never answered
"is this their course?", so every designer could edit, unpublish or delete every course — the
seeded pilot courses included. Role is a capability; ownership is an authorisation, and the two
need different code.

WHY IT RESOLVES UP THE TREE

Content mutations do not all name a course. A designer edits a CONTENT BLOCK, which belongs to a
section, which belongs to a lesson, which belongs to a module, which belongs to a course. Guarding
only `PUT /courses/{id}` while leaving `PUT /content-blocks/{id}` open would be a guard in name
only, so each entry point resolves the owning course from whatever id it holds.

THE NULL RULE

`Course.created_by` is NULL for seeded courses and for everything that predates the column. NULL
means SYSTEM-OWNED and only an admin may edit it. That is deliberately the conservative reading:
the alternative — treating unowned as "anyone may edit" — would leave the pilot content exactly
as exposed as it was before, which is the situation this exists to end.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import ContentBlock, Course, Lesson, Module, Section
from app.models.user import Role, User


def _forbidden(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": {"code": "NOT_COURSE_OWNER", "message": message}},
    )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": {"code": "NOT_FOUND", "message": "Course not found"}},
    )


def can_edit(user: User, course: Course) -> bool:
    """Whether `user` may modify `course`, as a plain predicate.

    Shares its rule with `assert_can_edit_course` so the authorisation lives in ONE place. The
    designer UI needs the answer without provoking a 403 — a course list that renders Edit and
    Delete on rows the API will refuse is a list that teaches people to distrust its buttons —
    and re-deriving "admin, or created_by is me" in TypeScript would be the same rule written
    twice, in two languages, to drift apart.
    """
    if user.role == Role.admin:
        return True
    return course.created_by is not None and course.created_by == user.id


async def assert_can_edit_course(
    db: AsyncSession, user: User, course_id: uuid.UUID
) -> Course:
    """Raise unless `user` may modify this course. Returns the course when they may.

    Admins may edit anything. A designer may edit only what they created; a course with no
    creator is system content and is admin-only.
    """
    course = (
        await db.execute(select(Course).where(Course.id == course_id))
    ).scalar_one_or_none()
    if course is None:
        raise _not_found()

    if can_edit(user, course):
        return course

    if course.created_by is None:
        raise _forbidden(
            "This is system content (a seeded course) and can only be edited by an administrator"
        )
    raise _forbidden("You can only edit courses you created")


async def _course_id_from(db: AsyncSession, stmt) -> uuid.UUID:
    course_id = (await db.execute(stmt)).scalars().first()
    if course_id is None:
        raise _not_found()
    return course_id


async def assert_can_edit_module(
    db: AsyncSession, user: User, module_id: uuid.UUID
) -> Course:
    course_id = await _course_id_from(
        db, select(Module.course_id).where(Module.id == module_id)
    )
    return await assert_can_edit_course(db, user, course_id)


async def assert_can_edit_lesson(
    db: AsyncSession, user: User, lesson_id: uuid.UUID
) -> Course:
    course_id = await _course_id_from(
        db,
        select(Module.course_id)
        .join(Lesson, Lesson.module_id == Module.id)
        .where(Lesson.id == lesson_id),
    )
    return await assert_can_edit_course(db, user, course_id)


async def assert_can_edit_section(
    db: AsyncSession, user: User, section_id: uuid.UUID
) -> Course:
    course_id = await _course_id_from(
        db,
        select(Module.course_id)
        .join(Lesson, Lesson.module_id == Module.id)
        .join(Section, Section.lesson_id == Lesson.id)
        .where(Section.id == section_id),
    )
    return await assert_can_edit_course(db, user, course_id)


async def assert_can_edit_block(
    db: AsyncSession, user: User, block_id: uuid.UUID
) -> Course:
    course_id = await _course_id_from(
        db,
        select(Module.course_id)
        .join(Lesson, Lesson.module_id == Module.id)
        .join(Section, Section.lesson_id == Lesson.id)
        .join(ContentBlock, ContentBlock.section_id == Section.id)
        .where(ContentBlock.id == block_id),
    )
    return await assert_can_edit_course(db, user, course_id)
