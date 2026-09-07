"""Snapshot a course's content at publish, and resolve which snapshot a learner is on.

WHY SNAPSHOT AT PUBLISH RATHER THAN ON EVERY EDIT

Autosave fires every couple of seconds while a designer types. Versioning that would produce
hundreds of snapshots per paragraph and make the history useless for the thing it exists for —
telling apart "the content a measurement was taken on" from "the content now". Publish is the
moment a designer asserts the content is ready for learners, which is exactly the boundary that
matters.

WHY THE SNAPSHOT IS TAKEN EVEN WHEN NOTHING CHANGED

Republishing an unchanged course still writes a version. Deduplicating would mean comparing trees
and deciding what counts as a change, and getting that wrong in the quiet direction — deciding
two trees are identical when they are not — silently reattaches new measurements to old content.
A redundant row is cheap; a wrong attribution is not.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fastapi import HTTPException, status

from app.models.content_version import ContentVersion
from app.models.course import Course, Lesson, Module, Section
from app.models.user import User

logger = structlog.get_logger(__name__)


def _block(block) -> dict[str, Any]:
    return {
        "id": str(block.id),
        "block_type": getattr(block.block_type, "value", block.block_type),
        "content": block.content,
        "sort_order": block.sort_order,
        "variant_key": block.variant_key,
    }


def _section(section) -> dict[str, Any]:
    return {
        "id": str(section.id),
        "title": section.title,
        "sort_order": section.sort_order,
        "estimated_duration_minutes": section.estimated_duration_minutes,
        "content_blocks": [
            _block(b) for b in sorted(section.content_blocks or [], key=lambda b: b.sort_order or 0)
        ],
    }


def _lesson(lesson) -> dict[str, Any]:
    return {
        "id": str(lesson.id),
        "title": lesson.title,
        "description": lesson.description,
        "sort_order": lesson.sort_order,
        "sections": [
            _section(s) for s in sorted(lesson.sections or [], key=lambda s: s.sort_order or 0)
        ],
    }


def _module(module) -> dict[str, Any]:
    return {
        "id": str(module.id),
        "title": module.title,
        "description": module.description,
        "sort_order": module.sort_order,
        "lessons": [
            _lesson(le) for le in sorted(module.lessons or [], key=lambda le: le.sort_order or 0)
        ],
    }


def build_snapshot(course: Course) -> dict[str, Any]:
    """The course's content tree as plain JSON-able data.

    Children are sorted by `sort_order` rather than left in load order, so two snapshots of the
    same content compare equal regardless of how the rows came back from the database. Ids are
    kept: without them a snapshot cannot be matched to the `section_id` a measurement carries,
    which is the whole point of taking it.
    """
    return {
        "course": {
            "id": str(course.id),
            "title": course.title,
            "description": course.description,
            "learning_objectives": course.learning_objectives,
            "estimated_duration_minutes": course.estimated_duration_minutes,
        },
        "modules": [
            _module(m) for m in sorted(course.modules or [], key=lambda m: m.sort_order or 0)
        ],
    }


async def _load_tree(db: AsyncSession, course_id: uuid.UUID) -> Course | None:
    return (
        await db.execute(
            select(Course)
            .where(Course.id == course_id)
            .options(
                selectinload(Course.modules)
                .selectinload(Module.lessons)
                .selectinload(Lesson.sections)
                .selectinload(Section.content_blocks)
            )
        )
    ).scalar_one_or_none()


async def snapshot_on_publish(
    db: AsyncSession, *, course_id: uuid.UUID, published_by: uuid.UUID | None
) -> ContentVersion | None:
    """Freeze the current content tree as a new version and point the course at it.

    Does NOT commit — the caller owns the transaction, so the version and the `is_published`
    flag that occasioned it are written together or not at all.

    Never raises. A failure to snapshot must not fail the publish: the designer's intent was to
    make the course available to learners, and refusing that because an audit record could not be
    written would be the wrong trade. The failure is logged loudly instead.
    """
    try:
        course = await _load_tree(db, course_id)
        if course is None:
            return None

        next_number = int(
            (
                await db.execute(
                    select(func.coalesce(func.max(ContentVersion.version_number), 0)).where(
                        ContentVersion.course_id == course_id
                    )
                )
            ).scalar_one()
            or 0
        ) + 1

        version = ContentVersion(
            course_id=course_id,
            version_number=next_number,
            snapshot=build_snapshot(course),
            published_by=published_by,
        )
        db.add(version)
        await db.flush()

        course.published_version_id = version.id
        await db.flush()

        logger.info(
            "content_version_published",
            course_id=str(course_id),
            version_number=next_number,
        )
        return version
    except Exception:  # noqa: BLE001 — an audit record must not block publishing
        logger.exception("content_version_snapshot_failed", course_id=str(course_id))
        return None


async def published_version_id(
    db: AsyncSession, *, section_id: uuid.UUID
) -> uuid.UUID | None:
    """The current published version of the course a section belongs to, or None.

    Used to stamp a completion with the content it was recorded against. Best-effort: returns
    None rather than raising, because failing to attribute a completion is better than failing
    to record one.
    """
    try:
        return (
            await db.execute(
                select(Course.published_version_id)
                .join(Module, Module.course_id == Course.id)
                .join(Lesson, Lesson.module_id == Module.id)
                .join(Section, Section.lesson_id == Lesson.id)
                .where(Section.id == section_id)
            )
        ).scalars().first()
    except Exception:  # noqa: BLE001
        logger.warning("published_version_lookup_failed", section_id=str(section_id))
        return None


async def list_versions(
    db: AsyncSession, course_id: uuid.UUID
) -> list[tuple[ContentVersion, str | None]]:
    """Published versions of a course, newest first, each with its publisher's name.

    Snapshots are deliberately NOT loaded here. One snapshot is the whole content tree of a
    course; a list of twenty would be megabytes to render a table of dates.

    The publisher is resolved to a display name rather than returned as a user id, because "who
    published this" is the question the history answers and a UUID does not answer it.
    """
    stmt = (
        select(ContentVersion, User.first_name, User.last_name)
        .outerjoin(User, User.id == ContentVersion.published_by)
        .where(ContentVersion.course_id == course_id)
        .order_by(ContentVersion.version_number.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        (
            version,
            f"{first} {last}".strip() if first or last else None,
        )
        for version, first, last in rows
    ]


async def get_version(db: AsyncSession, version_id: uuid.UUID) -> ContentVersion:
    """One version WITH its snapshot."""
    version = (
        await db.execute(select(ContentVersion).where(ContentVersion.id == version_id))
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Version not found"}},
        )
    return version
