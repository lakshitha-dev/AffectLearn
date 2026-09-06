"""Assessment API endpoints.

Story 6.5: `submit_attempt` now emits a best-effort `exercise_attempted` research event via the
non-blocking `_safe_emit` wrapper (mirroring `questionnaire.py` / `section_progress.py`). The
payload carries only research-safe fields (assessment/module ids, score/max_score, type), never
raw answer content. Emission NEVER blocks or crashes the learner's request (NFR22) — the durable
record is the attempt row. `phase`/`group` are resolved best-effort via `study_service`.
"""

import time
import uuid
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.models.user import Role, User
from app.schemas.assessment import (
    AssessmentCreate, AssessmentQuestionCreate, AssessmentQuestionDetailResponse,
    AssessmentResponse, AssessmentWithQuestionsResponse,
    AttemptCreate, AttemptResponse,
)
from app.services import assessment_service, study_service
from app.services.research_logger import emit as emit_research_event

logger = structlog.get_logger(__name__)

router = APIRouter()


def _now_ms() -> int:
    return int(time.time() * 1000)


async def _course_id_for(db: AsyncSession, assessment_id: uuid.UUID) -> str | None:
    """The course an assessment belongs to, for the migration-021 `course_id` coordinate.

    Pre/post assessment scores are the learning-gain measure, so they are the events most in
    need of a course key -- an attempt that cannot be attributed to a course cannot contribute
    to a per-course outcome. Assessments hang off a MODULE, not a section, so this cannot go
    through `content_context_service` and takes its own two-hop join.

    Best-effort: returns None on any failure rather than propagating, matching every other
    research-emission path on this route (NFR22).
    """
    try:
        from app.models.assessment import Assessment
        from app.models.course import Module

        return str(
            (
                await db.execute(
                    select(Module.course_id)
                    .join(Assessment, Assessment.module_id == Module.id)
                    .where(Assessment.id == assessment_id)
                )
            ).scalar_one()
        )
    except Exception:  # noqa: BLE001 — a missing coordinate must not fail an attempt
        logger.warning("assessment_course_lookup_failed", assessment_id=str(assessment_id))
        return None


async def _safe_emit(event: dict) -> None:
    """Emit a research event without ever propagating exceptions to the caller (NFR22)."""
    try:
        await emit_research_event(event)
    except Exception:
        logger.exception(
            "research_event_emit_swallowed", event_type=event.get("event_type")
        )


@router.post("", response_model=AssessmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assessment(
    body: AssessmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    return await assessment_service.create_assessment(db, data=body)


@router.post("/{assessment_id}/questions", response_model=AssessmentQuestionDetailResponse, status_code=status.HTTP_201_CREATED)
async def add_question(
    assessment_id: uuid.UUID,
    body: AssessmentQuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    return await assessment_service.add_question(db, assessment_id=assessment_id, data=body)


@router.get("", response_model=AssessmentWithQuestionsResponse)
async def get_assessment(
    module_id: uuid.UUID = Query(...),
    type: Literal["pre", "post"] = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    assessment = await assessment_service.get_assessment_by_module(
        db, module_id=module_id, assessment_type=type
    )
    if assessment is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ASSESSMENT_NOT_FOUND", "message": "Assessment not found"}},
        )
    return await assessment_service.get_assessment_for_learner(
        db, assessment_id=assessment.id, user_id=current_user.id
    )


@router.get("/{assessment_id}/attempts/latest", response_model=AttemptResponse)
async def get_latest_attempt(
    assessment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    attempt = await assessment_service.get_latest_attempt(
        db, user_id=current_user.id, assessment_id=assessment_id
    )
    if attempt is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "No attempt found"}},
        )
    # Reload assessment with questions+options for building the result payload
    assessment = await assessment_service.get_assessment_detail(db, assessment_id)
    return await assessment_service.build_attempt_response(db, attempt, assessment)


@router.post("/{assessment_id}/attempts", response_model=AttemptResponse, status_code=status.HTTP_201_CREATED)
async def submit_attempt(
    assessment_id: uuid.UUID,
    body: AttemptCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    result = await assessment_service.submit_attempt(
        db,
        user_id=current_user.id,
        assessment_id=assessment_id,
        answers=body.answers,
        started_at=body.started_at,
    )

    # Story 6.5: best-effort `exercise_attempted` research event (research-safe fields only —
    # ids + score, never raw answers). Never blocks the response.
    try:
        phase = await study_service.get_phase(db)
        group = await study_service.get_group(db, current_user.id)
    except Exception:
        logger.exception("research_phase_group_resolution_failed")
        phase = group = None
    course_id = await _course_id_for(db, assessment_id)
    await _safe_emit({
        "event_type": "exercise_attempted",
        "learner_id": str(current_user.id),
        "session_id": None,
        "cycle_number": 0,
        "timestamp": _now_ms(),
        "phase": phase,
        "group": group,
        # No section coordinate: an assessment spans a module, not a section.
        **({"course_id": course_id} if course_id else {}),
        "payload": {
            "assessment_id": str(assessment_id),
            "score": getattr(result, "score", None),
            "max_score": getattr(result, "max_score", None),
            "attempt": int(getattr(result, "attempt_number", 0) or 0),
        },
    })
    return result