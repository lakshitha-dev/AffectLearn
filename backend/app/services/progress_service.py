"""Learner progress aggregation (Story 4.6).

Read-only rollup used by the learner-progress endpoint and (optionally) the Learner
Profiler to inform `topic_mastery`. Reuses the course→lesson→module→section joins from
`section_progress_service`. Pure reads; no writes.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course, Lesson, Module, Section
from app.models.enrollment import Enrollment
from app.models.quiz_response import QuizBlockResponse
from app.models.section_progress import SectionProgress


def _as_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _empty() -> dict[str, Any]:
    return {"courses": [], "sections": [], "quizzes": {"answered": 0, "correct": 0}}


async def get_learner_progress(db: AsyncSession, user_id: Any) -> dict[str, Any]:
    """Aggregate a learner's progress: per-course completion, section entries, quiz tally."""
    uid = _as_uuid(user_id)
    if uid is None:
        return _empty()

    enrolled = (
        await db.execute(
            select(Course.id, Course.title)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .where(Enrollment.user_id == uid)
        )
    ).all()
    course_ids = [row[0] for row in enrolled]

    totals: dict[Any, int] = {}
    completed: dict[Any, int] = {}
    if course_ids:
        total_rows = (
            await db.execute(
                select(Module.course_id, func.count(Section.id))
                .select_from(Section)
                .join(Lesson, Section.lesson_id == Lesson.id)
                .join(Module, Lesson.module_id == Module.id)
                .where(Module.course_id.in_(course_ids))
                .group_by(Module.course_id)
            )
        ).all()
        totals = {r[0]: r[1] for r in total_rows}

        completed_rows = (
            await db.execute(
                select(Module.course_id, func.count(SectionProgress.id))
                .select_from(SectionProgress)
                .join(Section, SectionProgress.section_id == Section.id)
                .join(Lesson, Section.lesson_id == Lesson.id)
                .join(Module, Lesson.module_id == Module.id)
                .where(SectionProgress.user_id == uid, Module.course_id.in_(course_ids))
                .group_by(Module.course_id)
            )
        ).all()
        completed = {r[0]: r[1] for r in completed_rows}

    courses = []
    for cid, title in enrolled:
        total = totals.get(cid, 0)
        done = completed.get(cid, 0)
        courses.append({
            "course_id": cid,
            "course_title": title,
            "total_sections": total,
            "completed_sections": done,
            "percentage": (done * 100.0 / total) if total else 0.0,
        })

    section_rows = (
        await db.execute(
            select(
                SectionProgress.section_id,
                SectionProgress.completed_at,
                SectionProgress.time_spent_seconds,
                SectionProgress.affect_states,
            ).where(SectionProgress.user_id == uid)
        )
    ).all()
    sections = [
        {
            "section_id": r[0],
            "completed_at": r[1],
            "time_spent_seconds": r[2],
            "affect_states": r[3],
        }
        for r in section_rows
    ]

    answered = (
        await db.execute(
            select(func.count(QuizBlockResponse.id)).where(QuizBlockResponse.user_id == uid)
        )
    ).scalar_one()
    correct = (
        await db.execute(
            select(func.count(QuizBlockResponse.id)).where(
                QuizBlockResponse.user_id == uid, QuizBlockResponse.is_correct.is_(True)
            )
        )
    ).scalar_one()

    return {
        "courses": courses,
        "sections": sections,
        "quizzes": {"answered": int(answered), "correct": int(correct)},
    }
