"""Section progress and quiz response API endpoints.

Story 6.5: these learner-interaction endpoints now emit best-effort research events
(`section_started` / `section_completed` on the section-progress route, `quiz_submitted` on the
quiz-response route) via the non-blocking `_safe_emit` wrapper — mirroring `questionnaire.py` /
`ws.py`. Emission NEVER blocks or crashes the learner's request (NFR22): the durable record is
always the DB row; the research event is fire-and-forget. Payloads carry only research-safe,
non-PII fields (ids + correctness), never raw answer content. `phase`/`group` are resolved
best-effort via `study_service` (these routes are not in the latency-critical agent loop).
"""

import time
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_db, require_role
from app.models.quiz_response import QuizBlockResponse
from app.models.user import Role, User
from app.schemas.base import CamelModel
from app.schemas.section_progress import (
    CourseProgressResponse,
    LessonProgressResponse,
    SectionProgressCreate,
    SectionProgressResponse,
)
from app.services import (
    assistance_service,
    attempt_service,
    content_context_service,
    section_progress_service,
    study_service,
)
from app.services.research_logger import content_coords
from app.services.research_logger import emit as emit_research_event

logger = structlog.get_logger(__name__)

router = APIRouter()


def _now_ms() -> int:
    return int(time.time() * 1000)


async def _safe_emit(event: dict) -> None:
    """Emit a research event without ever propagating exceptions to the caller (NFR22)."""
    try:
        await emit_research_event(event)
    except Exception:
        logger.exception(
            "research_event_emit_swallowed", event_type=event.get("event_type")
        )


async def _resolve_phase_group(db: AsyncSession, user_id) -> tuple[str | None, str | None]:
    """Best-effort (phase, group) for a REST emit; never raises (→ (None, None) on failure)."""
    try:
        phase = await study_service.get_phase(db)
        group = await study_service.get_group(db, user_id)
        return phase, group
    except Exception:
        logger.exception("research_phase_group_resolution_failed")
        return None, None


class QuizResponseCreate(CamelModel):
    content_block_id: uuid.UUID
    selected_answers: list[str]
    is_correct: bool
    # Behavioral-data probe (frustration/deliberation signal): time from first seeing the
    # quiz to submitting, and the section it belongs to. Optional/back-compatible.
    response_time_ms: int | None = None
    section_id: uuid.UUID | None = None
    # Migration 022: the server-issued `adaptation_id` of the help on screen when the learner
    # answered, echoed back by the client. This is the join that turns "a hint was shown" into
    # "a hint was shown and the next attempt was correct". Optional, and absent for the great
    # majority of answers, which follow no intervention at all.
    assistance_id: str | None = None


class QuizResponseOut(CamelModel):
    id: uuid.UUID
    content_block_id: uuid.UUID
    is_correct: bool
    model_config = ConfigDict(from_attributes=True)


@router.post(
    "/section-progress",
    response_model=SectionProgressResponse,
    tags=["section-progress"],
)
async def mark_section_complete(
    body: SectionProgressCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    """Mark a section complete (idempotent).

    Returns 201 on first completion; 200 on subsequent (already complete) calls.
    """
    progress, created = await section_progress_service.mark_section_complete(
        db,
        user_id=current_user.id,
        section_id=body.section_id,
        time_spent_seconds=body.time_spent_seconds,
        affect_states=body.affect_states,
    )
    response.status_code = (
        status.HTTP_201_CREATED if created else status.HTTP_200_OK
    )

    # Story 6.5: best-effort research events. On the FIRST completion (`created`) the section's
    # engagement is first recorded, so emit `section_started` then `section_completed`; an
    # idempotent re-completion emits only `section_completed`. Never blocks the response.
    phase, group = await _resolve_phase_group(db, current_user.id)
    now = _now_ms()
    base = {
        "learner_id": str(current_user.id),
        "session_id": None,
        "cycle_number": 0,
        "phase": phase,
        "group": group,
        # Migration 021 content coordinates. Resolved through the same cached lookup the agent
        # loop uses, so a section's REST events and its affect cycles carry identical keys and
        # join without a translation step. The payload copy of `section_id` is retained for
        # existing readers (`section_features` pairs on it).
        **content_coords(await content_context_service.build(body.section_id, db)),
    }
    payload = {
        "section_id": str(body.section_id),
        "time_spent_seconds": body.time_spent_seconds,
    }
    if created:
        await _safe_emit({
            **base, "event_type": "section_started", "timestamp": now, "payload": payload,
        })
    await _safe_emit({
        **base,
        "event_type": "section_completed",
        "timestamp": _now_ms(),
        "payload": {**payload, "created": created},
    })

    # Per-section confusion features (ships DARK — logged for future training, never fed to the
    # live model, whose input width is frozen by the deployed ONNX). Emitted here so the feature
    # row and the `self_report` label for the same section land in the same store and pair on
    # learner_id + section_id. Best-effort throughout: a failure here must not affect completion.
    await _safe_emit_section_features(
        db, base=base, signals=body.interaction_signals, section_id=body.section_id
    )
    return progress


async def _safe_emit_section_features(
    db: AsyncSession, *, base: dict, signals, section_id
) -> None:
    """Emit the `section_features` row for a completed section. Never raises.

    Counters come from the CLIENT (`signals`), not from reading research events back: `emit`
    publishes to a Redis stream that a worker later drains into Postgres, so a section's events
    are not queryable at completion time — and are lost entirely when Redis is down. The lesson
    page already holds them, so they ride along in the completion body instead.

    Section shape is read from the DB, which is durable and already loaded for this request path.
    """
    try:
        from app.models.course import Section
        from app.services import section_features

        shape = {}
        section = (
            await db.execute(
                select(Section)
                .options(selectinload(Section.content_blocks))
                .where(Section.id == section_id)
            )
        ).scalar_one_or_none()
        if section is not None:
            shape = section_features.section_shape_from_blocks(section.content_blocks or [])

        features = section_features.from_signals(
            signals.model_dump() if hasattr(signals, "model_dump") else signals,
            str(section_id),
            section_shape=shape,
        )
    except Exception:  # noqa: BLE001 — dark-shipped instrumentation, never break a completion
        logger.exception("section_features_extraction_failed", section_id=str(section_id))
        return

    await _safe_emit({
        **base,
        "event_type": "section_features",
        "timestamp": _now_ms(),
        "payload": features,
    })


@router.get(
    "/lessons/{lesson_id}/progress",
    response_model=LessonProgressResponse,
    tags=["section-progress"],
)
async def get_lesson_progress(
    lesson_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    return await section_progress_service.get_lesson_progress(
        db, user_id=current_user.id, lesson_id=lesson_id
    )


@router.get(
    "/courses/{course_id}/progress",
    response_model=CourseProgressResponse,
    tags=["section-progress"],
)
async def get_course_progress(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    return await section_progress_service.get_course_progress(
        db, user_id=current_user.id, course_id=course_id
    )


@router.post(
    "/quiz-responses",
    response_model=QuizResponseOut,
    tags=["section-progress"],
    status_code=status.HTTP_201_CREATED,
)
async def record_quiz_response(
    body: QuizResponseCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    """Record a quiz/exercise response.

    TWO RECORDS, ON PURPOSE (migration 022).

    `quiz_responses` is the per-block SUMMARY and keeps the behaviour it has always had: one row
    per (learner, block), first answer wins, repeat submissions return 200 with the original row.
    `progress_service` counts it for "quizzes answered / correct", and redefining that mid-study
    would silently move every learner's reported accuracy.

    `quiz_attempts` is the HISTORY and is appended to on EVERY submission, including the repeats
    the summary discards. Before this, a learner who answered wrongly, received a hint, and then
    answered correctly left a durable record that said only "wrong" -- so attempt counts,
    repeated mistakes, per-attempt timing and "did they succeed after being helped" had no
    answer outside a best-effort research log.

    The attempt is written in the SAME transaction as the summary row, so the two can never
    disagree about whether the answer was saved.
    """
    existing = (
        await db.execute(
            select(QuizBlockResponse).where(
                QuizBlockResponse.user_id == current_user.id,
                QuizBlockResponse.content_block_id == body.content_block_id,
            )
        )
    ).scalar_one_or_none()

    attempt = await attempt_service.record_quiz_attempt(
        db,
        user_id=current_user.id,
        content_block_id=body.content_block_id,
        selected_answers=body.selected_answers,
        is_correct=body.is_correct,
        section_id=body.section_id,
        response_time_ms=body.response_time_ms,
        assistance_id=body.assistance_id,
    )

    if existing is not None:
        # The summary already exists, but this attempt is new and must still be persisted --
        # this path used to return without committing anything at all.
        await _resolve_assistance_outcome(db, body, attempt)
        await db.commit()
        response.status_code = status.HTTP_200_OK
        _log_attempt(attempt, current_user.id, body.content_block_id)
        await _emit_quiz_submitted(db, current_user, body, attempt)
        return existing

    record = QuizBlockResponse(
        user_id=current_user.id,
        content_block_id=body.content_block_id,
        selected_answers=body.selected_answers,
        is_correct=body.is_correct,
    )
    db.add(record)
    await _resolve_assistance_outcome(db, body, attempt)
    try:
        await db.commit()
    except IntegrityError:
        # A concurrent first submission won the race. The rollback discards OUR attempt row too,
        # so it is re-recorded against the now-committed summary rather than silently lost.
        await db.rollback()
        existing = (
            await db.execute(
                select(QuizBlockResponse).where(
                    QuizBlockResponse.user_id == current_user.id,
                    QuizBlockResponse.content_block_id == body.content_block_id,
                )
            )
        ).scalar_one_or_none()
        attempt = await attempt_service.record_quiz_attempt(
            db,
            user_id=current_user.id,
            content_block_id=body.content_block_id,
            selected_answers=body.selected_answers,
            is_correct=body.is_correct,
            section_id=body.section_id,
            response_time_ms=body.response_time_ms,
            assistance_id=body.assistance_id,
        )
        await _resolve_assistance_outcome(db, body, attempt)
        await db.commit()
        response.status_code = status.HTTP_200_OK
        await _emit_quiz_submitted(db, current_user, body, attempt)
        return existing
    await db.refresh(record)
    _log_attempt(attempt, current_user.id, body.content_block_id)
    await _emit_quiz_submitted(db, current_user, body, attempt)
    return record


async def _resolve_assistance_outcome(db, body, attempt) -> None:
    """Record this answer against the help that was on screen when it was given (migration 023).

    Resolved here rather than by a background pass so it lands in the SAME transaction as the
    attempt: the ledger can never claim an outcome for an attempt that was rolled back.

    An ASSOCIATION, not a cause. The learner may have answered correctly despite the hint,
    ignored it, or been helped by re-reading the section. Surfaces built on this must say which
    of the two they are asserting.
    """
    if attempt is None or not body.assistance_id:
        return
    await assistance_service.resolve_outcome(
        db,
        adaptation_id=body.assistance_id,
        attempt_id=attempt.id,
        is_correct=bool(body.is_correct),
    )


def _log_attempt(attempt, user_id, content_block_id) -> None:
    """Surface a failed history write. The answer was still saved; the history was not."""
    if attempt is None:
        logger.warning(
            "quiz_attempt_not_recorded",
            user_id=str(user_id),
            content_block_id=str(content_block_id),
        )


async def _emit_quiz_submitted(db, current_user, body, attempt) -> None:
    """Best-effort `quiz_submitted` research event. Never blocks or fails the response."""
    # Story 6.5: research-safe fields only — the content-block id + correctness, never the raw
    # selected answers.
    phase, group = await _resolve_phase_group(db, current_user.id)
    await _safe_emit({
        "event_type": "quiz_submitted",
        "learner_id": str(current_user.id),
        "session_id": None,
        "cycle_number": 0,
        "timestamp": _now_ms(),
        "phase": phase,
        "group": group,
        # The only event that can name a BLOCK: a quiz response is an act on one content block,
        # which is the grain "which question is hardest" and the hint-to-outcome join both need.
        **content_coords(await content_context_service.build(body.section_id, db)),
        "block_id": str(body.content_block_id),
        "payload": {
            "content_block_id": str(body.content_block_id),
            "is_correct": bool(body.is_correct),
            "response_time_ms": body.response_time_ms,
            "section_id": str(body.section_id) if body.section_id else None,
            # Migration 022. Which attempt this was, and the help that was on screen when the
            # learner answered. `attempt_number` distinguishes a first-time correct answer from
            # one reached after three tries -- indistinguishable in the record until now.
            "attempt_number": getattr(attempt, "attempt_number", None),
            "assistance_id": getattr(attempt, "assistance_id", None),
        },
    })


# ── Section visits (migration 022) ──────────────────────────────────────────────
#
# `section_progress` records one COMPLETION per section. These record every VISIT, including the
# revisits that never end in a completion — which is the case most worth seeing, since returning
# to material is one of the few struggle signals this paginated interface produces reliably.


class SectionVisitCreate(CamelModel):
    section_id: uuid.UUID
    # How the learner arrived: "next" | "back" | "resume" | "direct". Free-form on the wire so a
    # new navigation affordance needs no migration; an unrecognised value is still a fact.
    entry_source: str | None = None


class SectionVisitOut(CamelModel):
    id: uuid.UUID
    section_id: uuid.UUID
    model_config = ConfigDict(from_attributes=True)


class SectionVisitClose(CamelModel):
    # Seconds the learner spent on the section, as measured by the client. Optional: the server
    # can bound it from the timestamps, but only the client can exclude time the tab was hidden.
    duration_seconds: int | None = None


@router.post(
    "/section-visits",
    response_model=SectionVisitOut,
    tags=["section-progress"],
    status_code=status.HTTP_201_CREATED,
)
async def open_section_visit(
    body: SectionVisitCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    """Open a visit when a learner lands on a section. Returns the id used to close it."""
    enrollment_id = await _enrollment_id_for_section(db, current_user.id, body.section_id)
    visit = await attempt_service.open_visit(
        db,
        user_id=current_user.id,
        section_id=body.section_id,
        enrollment_id=enrollment_id,
        entry_source=body.entry_source,
    )
    if visit is None:
        # Instrumentation must never block learning: report the failure rather than 500-ing a
        # learner out of a section they were about to read.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "VISIT_NOT_RECORDED",
                              "message": "Could not open a visit for that section"}},
        )
    await db.commit()
    return visit


@router.post(
    "/section-visits/{visit_id}/close",
    response_model=SectionVisitOut,
    tags=["section-progress"],
)
async def close_section_visit(
    visit_id: uuid.UUID,
    body: SectionVisitClose,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    """Close a visit when the learner navigates away.

    Idempotent: the browser sends this from both a navigation handler and an unload handler, and
    both firing is normal. Scoped to the caller, so one learner cannot close another's visit.
    """
    visit = await attempt_service.close_visit(
        db,
        visit_id=visit_id,
        user_id=current_user.id,
        duration_seconds=body.duration_seconds,
    )
    if visit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "VISIT_NOT_FOUND", "message": "No such visit"}},
        )
    await db.commit()
    return visit


async def _enrollment_id_for_section(db: AsyncSession, user_id, section_id):
    """The caller's enrollment in the course this section belongs to, or None.

    Best-effort: a visit is worth recording even when the enrollment cannot be resolved (a shared
    link into an unenrolled course still tells you the section was opened), so this degrades to
    None rather than refusing the visit.
    """
    try:
        from app.models.course import Lesson, Module, Section
        from app.models.enrollment import Enrollment

        return (
            await db.execute(
                select(Enrollment.id)
                .join(Module, Module.course_id == Enrollment.course_id)
                .join(Lesson, Lesson.module_id == Module.id)
                .join(Section, Section.lesson_id == Lesson.id)
                .where(Section.id == section_id, Enrollment.user_id == user_id)
            )
        ).scalars().first()
    except Exception:  # noqa: BLE001
        logger.warning("visit_enrollment_lookup_failed", section_id=str(section_id))
        return None
