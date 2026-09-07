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
    AssessmentAuthoringResponse,
    AssessmentQuestionUpdate,
    AssessmentUpdate,
    AssessmentCreate, AssessmentQuestionCreate, AssessmentQuestionDetailResponse,
    AssessmentResponse, AssessmentWithQuestionsResponse,
    AttemptCreate, AttemptResponse,
)
from app.services import assessment_service, course_ownership, study_service
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


async def _assert_can_edit_assessment(
    db: AsyncSession, user: User, assessment_id: uuid.UUID
) -> None:
    """Resolve an assessment to its module and apply the course-ownership rule.

    An assessment names a module, not a course, so the ownership check has to walk up the same
    way the content guards do.
    """
    from app.models.assessment import Assessment

    module_id = (
        await db.execute(
            select(Assessment.module_id).where(Assessment.id == assessment_id)
        )
    ).scalars().first()
    if module_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Assessment not found"}},
        )
    await course_ownership.assert_can_edit_module(db, user, module_id)


@router.post("", response_model=AssessmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assessment(
    body: AssessmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    # Scoped to the owning course. Being a designer said nothing about WHOSE module this is, so
    # a designer could hang a pre-assessment off another designer's course.
    await course_ownership.assert_can_edit_module(db, current_user, body.module_id)
    return await assessment_service.create_assessment(db, data=body)


@router.post("/{assessment_id}/questions", response_model=AssessmentQuestionDetailResponse, status_code=status.HTTP_201_CREATED)
async def add_question(
    assessment_id: uuid.UUID,
    body: AssessmentQuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await _assert_can_edit_assessment(db, current_user, assessment_id)
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

# ---------------------------------------------------------------------------
# Authoring (designer-facing)
# ---------------------------------------------------------------------------
#
# `POST /assessments` and `POST /{id}/questions` were role-guarded, tested and never called by
# anything — so FR9's pre/post assessments could only be brought into existence by hand-crafted
# HTTP requests, and once created could not be listed, corrected or removed. These complete the
# set an authoring screen needs.
#
# All of them read the correct answers back, which is why they are separate from the learner
# routes above rather than a flag on them: `AssessmentOptionResponse` omits `is_correct` on
# purpose, and the safest way to keep it omitted is for the learner path never to have a branch
# that includes it.


@router.get("/by-module/{module_id}", response_model=list[AssessmentAuthoringResponse])
async def list_assessments_for_module(
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    """Both assessments for a module, with answers — the authoring view."""
    await course_ownership.assert_can_edit_module(db, current_user, module_id)
    return await assessment_service.list_assessments_for_module(db, module_id)


@router.put("/{assessment_id}", response_model=AssessmentResponse)
async def update_assessment(
    assessment_id: uuid.UUID,
    body: AssessmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    await _assert_can_edit_assessment(db, current_user, assessment_id)
    return await assessment_service.update_assessment(db, assessment_id, title=body.title)


@router.delete("/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assessment(
    assessment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    """Withdraw an assessment. Learner attempts against it go too — see the service."""
    await _assert_can_edit_assessment(db, current_user, assessment_id)
    await assessment_service.delete_assessment(db, assessment_id)


@router.put("/questions/{question_id}", response_model=AssessmentQuestionDetailResponse)
async def update_question(
    question_id: uuid.UUID,
    body: AssessmentQuestionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    question = await assessment_service.get_question_or_404(db, question_id)
    await _assert_can_edit_assessment(db, current_user, question.assessment_id)
    return await assessment_service.update_question(
        db,
        question_id,
        text=body.text,
        sort_order=body.sort_order,
        explanation=body.explanation,
        options=body.options,
    )


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    question = await assessment_service.get_question_or_404(db, question_id)
    await _assert_can_edit_assessment(db, current_user, question.assessment_id)
    await assessment_service.delete_question(db, question_id)
