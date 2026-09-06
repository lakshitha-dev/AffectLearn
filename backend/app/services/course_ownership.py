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


# --- READ authorisation -------------------------------------------------------------------
#
# Editing was guarded above; reading was not. `course_service.get_course` applies no
# `is_published` filter, so any authenticated learner holding a course UUID could pull the whole
# draft tree — unpublished modules, unreleased lessons, and every content block inside them. The
# LIST endpoint has always filtered correctly (`published_only=is_learner`), which is what made
# the omission easy to miss: browsing behaved, and only a direct fetch by id did not.
#
# The rule mirrors the list endpoint exactly: a learner sees published courses, everyone else
# sees what they already saw. Designers deliberately keep read access to courses they do not own
# — the course list shows them every course with `canEdit: false` — so this narrows learners only.
#
# WHY 404 AND NOT 403
#
# Answering "forbidden" for an unpublished course confirms that a course with that id exists and
# is being worked on. A learner has no business distinguishing "no such course" from "not yet
# released", so both answer the same way.


def can_read(user: User, course: Course) -> bool:
    """Whether `user` may read `course`. Learners are limited to published courses."""
    if user.role == Role.learner:
        return bool(course.is_published)
    return True


async def assert_can_read_course(
    db: AsyncSession, user: User, course_id: uuid.UUID
) -> Course:
    """Raise 404 unless `user` may read this course. Returns the course when they may."""
    course = (
        await db.execute(select(Course).where(Course.id == course_id))
    ).scalar_one_or_none()
    if course is None or not can_read(user, course):
        raise _not_found()
    return course


async def assert_can_read_module(
    db: AsyncSession, user: User, module_id: uuid.UUID
) -> Course:
    course_id = await _course_id_from(
        db, select(Module.course_id).where(Module.id == module_id)
    )
    return await assert_can_read_course(db, user, course_id)


async def assert_can_read_lesson(
    db: AsyncSession, user: User, lesson_id: uuid.UUID
) -> Course:
    course_id = await _course_id_from(
        db,
        select(Module.course_id)
        .join(Lesson, Lesson.module_id == Module.id)
        .where(Lesson.id == lesson_id),
    )
    return await assert_can_read_course(db, user, course_id)


async def assert_can_read_section(
    db: AsyncSession, user: User, section_id: uuid.UUID
) -> Course:
    course_id = await _course_id_from(
        db,
        select(Module.course_id)
        .join(Lesson, Lesson.module_id == Module.id)
        .join(Section, Section.lesson_id == Lesson.id)
        .where(Section.id == section_id),
    )
    return await assert_can_read_course(db, user, course_id)


# --- ANALYTICS authorisation --------------------------------------------------------------
#
# `/analytics/*` was `require_role(course_designer, admin)` with no course scoping, so any
# designer could read any other designer's course analytics — learner affect distributions,
# struggle leaderboards, per-paragraph confusion. The writes have always been scoped; the reads
# over the same tree were not.
#
# WHY THIS IS NOT `assert_can_edit_course`
#
# The obvious fix — reuse the edit guard — would break the pilot. Seeded courses have
# `created_by = NULL`, which the edit rule treats as admin-only system content (`canEdit: false`
# in the designer UI). The pilot runs on exactly such a course, so reusing the edit rule would
# lock every designer out of the analytics the platform exists to show them.
#
# The rule that actually matches the intent: shared/system content is visible to any designer,
# and a course with a named owner is visible to that owner (and to admins). That closes the
# cross-designer leak without pretending analytics and authoring are the same permission.


def can_view_analytics(user: User, course: Course) -> bool:
    """Whether `user` may read analytics for `course`."""
    if user.role == Role.admin:
        return True
    if course.created_by is None:
        return True  # system/seeded content is shared, and the pilot course is one of these
    return course.created_by == user.id


async def assert_can_view_course_analytics(
    db: AsyncSession, user: User, course_id: uuid.UUID
) -> Course:
    course = (
        await db.execute(select(Course).where(Course.id == course_id))
    ).scalar_one_or_none()
    if course is None:
        raise _not_found()
    if not can_view_analytics(user, course):
        raise _forbidden("You can only view analytics for courses you created")
    return course


async def assert_can_view_section_analytics(
    db: AsyncSession, user: User, section_id: uuid.UUID
) -> Course:
    course_id = await _course_id_from(
        db,
        select(Module.course_id)
        .join(Lesson, Lesson.module_id == Module.id)
        .join(Section, Section.lesson_id == Lesson.id)
        .where(Section.id == section_id),
    )
    return await assert_can_view_course_analytics(db, user, course_id)
