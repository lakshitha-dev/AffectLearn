"""Append-only attempt history: quiz attempts and section visits (migration 022).

WHY THIS IS A SERVICE RATHER THAN INLINE ROUTE CODE

Two callers need the same ordinal logic and the same never-break-the-learner discipline: the
quiz-response route records an attempt alongside the summary row it already writes, and the
assessment route needs the same per-(user, assessment) ordinal. Assigning an ordinal correctly
is the part worth having in one place -- see `next_attempt_number`.

FAILURE POSTURE

Recording history must never cost a learner their answer. Every function here either returns a
value or returns None after logging; none of them raise, and none of them commit -- the caller
owns the transaction, so an attempt row joins the same commit as the response it belongs to and
the two can never disagree about whether the answer was saved.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz_attempt import QuizAttempt
from app.models.section_visit import SectionVisit

logger = structlog.get_logger(__name__)


async def next_attempt_number(
    db: AsyncSession, *, user_id: uuid.UUID, content_block_id: uuid.UUID
) -> int:
    """The 1-based ordinal for a learner's next attempt at a block.

    Derived by counting, never taken from the client: a client-supplied ordinal lets a retried
    request overwrite an earlier attempt, which is precisely the loss this table exists to stop.

    Counting races under concurrency -- two submissions in flight could both read the same count
    and land on the same ordinal. That is accepted rather than locked against: a learner answers
    one question at a time in one session, the rows are still distinct and still ordered by
    `submitted_at`, and taking a row lock on the hot answer path would trade a real cost for a
    duplicate ordinal that no reader depends on being unique.
    """
    existing = (
        await db.execute(
            select(func.count(QuizAttempt.id)).where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.content_block_id == content_block_id,
            )
        )
    ).scalar_one()
    return int(existing or 0) + 1


async def record_quiz_attempt(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    content_block_id: uuid.UUID,
    selected_answers: Any,
    is_correct: bool,
    section_id: uuid.UUID | None = None,
    response_time_ms: int | None = None,
    assistance_id: str | None = None,
) -> QuizAttempt | None:
    """Append one attempt. Never raises; returns None if the row could not be built.

    Does NOT commit. The caller commits it together with the summary row, so history and summary
    are written atomically.
    """
    try:
        attempt = QuizAttempt(
            user_id=user_id,
            content_block_id=content_block_id,
            section_id=section_id,
            attempt_number=await next_attempt_number(
                db, user_id=user_id, content_block_id=content_block_id
            ),
            selected_answers=selected_answers,
            is_correct=bool(is_correct),
            response_time_ms=response_time_ms,
            # Trimmed rather than rejected: an over-long id is a client bug, and losing the whole
            # attempt row over it would be a worse outcome than losing the link.
            assistance_id=(str(assistance_id)[:64] if assistance_id else None),
        )
        db.add(attempt)
        await db.flush()
        return attempt
    except Exception:  # noqa: BLE001 — history must never cost a learner their answer
        logger.exception(
            "quiz_attempt_record_failed",
            user_id=str(user_id),
            content_block_id=str(content_block_id),
        )
        return None


async def attempts_for_block(
    db: AsyncSession, *, user_id: uuid.UUID, content_block_id: uuid.UUID
) -> list[QuizAttempt]:
    """A learner's attempts at one block, oldest first. The mistake-history read."""
    rows = (
        await db.execute(
            select(QuizAttempt)
            .where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.content_block_id == content_block_id,
            )
            .order_by(QuizAttempt.attempt_number.asc(), QuizAttempt.submitted_at.asc())
        )
    ).scalars().all()
    return list(rows)


async def first_attempt_after(
    db: AsyncSession, *, user_id: uuid.UUID, assistance_id: str
) -> QuizAttempt | None:
    """The first attempt a learner made while a given piece of help was on screen.

    This is the factual half of "did the hint work": the learner was shown help identified by
    `assistance_id`, and this is the answer they gave next. It is a recorded association, not a
    causal claim -- the learner may have solved it despite the hint, or ignored it entirely.
    Readers that present this must say which of the two they are asserting.
    """
    return (
        await db.execute(
            select(QuizAttempt)
            .where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.assistance_id == assistance_id,
            )
            .order_by(QuizAttempt.submitted_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def open_visit(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    section_id: uuid.UUID,
    enrollment_id: uuid.UUID | None = None,
    entry_source: str | None = None,
) -> SectionVisit | None:
    """Open a visit to a section. Never raises. Does NOT commit."""
    try:
        visit = SectionVisit(
            user_id=user_id,
            section_id=section_id,
            enrollment_id=enrollment_id,
            entry_source=(str(entry_source)[:16] if entry_source else None),
        )
        db.add(visit)
        await db.flush()
        return visit
    except Exception:  # noqa: BLE001
        logger.exception(
            "section_visit_open_failed",
            user_id=str(user_id), section_id=str(section_id),
        )
        return None


async def close_visit(
    db: AsyncSession,
    *,
    visit_id: uuid.UUID,
    user_id: uuid.UUID,
    duration_seconds: int | None = None,
) -> SectionVisit | None:
    """Close a previously opened visit. Never raises. Does NOT commit.

    Scoped by `user_id` as well as `visit_id` so one learner cannot close another's visit by
    guessing an id -- the id travels to the browser, so it is client-supplied on the way back.

    Closing an already-closed visit is a no-op rather than an error: the browser sends this from
    both a navigation handler and an unload handler, and both firing is normal.
    """
    try:
        visit = (
            await db.execute(
                select(SectionVisit).where(
                    SectionVisit.id == visit_id, SectionVisit.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if visit is None or visit.left_at is not None:
            return visit

        visit.left_at = func.now()
        if duration_seconds is not None and duration_seconds >= 0:
            visit.duration_seconds = int(duration_seconds)
        await db.flush()
        return visit
    except Exception:  # noqa: BLE001
        logger.exception("section_visit_close_failed", visit_id=str(visit_id))
        return None
