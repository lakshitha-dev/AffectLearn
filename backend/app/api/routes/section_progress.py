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
from fastapi import APIRouter, Depends, Response, status
from pydantic import ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.services import section_progress_service, study_service
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
    return progress


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
    """Record or update a quiz/exercise response (idempotent upsert)."""
    existing = (
        await db.execute(
            select(QuizBlockResponse).where(
                QuizBlockResponse.user_id == current_user.id,
                QuizBlockResponse.content_block_id == body.content_block_id,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return existing

    record = QuizBlockResponse(
        user_id=current_user.id,
        content_block_id=body.content_block_id,
        selected_answers=body.selected_answers,
        is_correct=body.is_correct,
    )
    db.add(record)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(QuizBlockResponse).where(
                    QuizBlockResponse.user_id == current_user.id,
                    QuizBlockResponse.content_block_id == body.content_block_id,
                )
            )
        ).scalar_one_or_none()
        response.status_code = status.HTTP_200_OK
        return existing
    await db.refresh(record)

    # Story 6.5: best-effort `quiz_submitted` research event (research-safe fields only — the
    # content-block id + correctness, never the raw selected answers). Never blocks the response.
    phase, group = await _resolve_phase_group(db, current_user.id)
    await _safe_emit({
        "event_type": "quiz_submitted",
        "learner_id": str(current_user.id),
        "session_id": None,
        "cycle_number": 0,
        "timestamp": _now_ms(),
        "phase": phase,
        "group": group,
        "payload": {
            "content_block_id": str(body.content_block_id),
            "is_correct": bool(body.is_correct),
            "response_time_ms": body.response_time_ms,
            "section_id": str(body.section_id) if body.section_id else None,
        },
    })
    return record
