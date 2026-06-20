"""Pre-study questionnaire API (Story 6.3).

`POST /onboarding/questionnaire` persists the authenticated learner's baseline answers
(the instrument's Sections A–E, Q1–Q14) and `GET /onboarding/questionnaire` returns the
caller's own submission (or 404 if none). Both endpoints require authentication and operate
ONLY on the caller's `user_id` — a `user_id` is NEVER read from the request body, so a
learner cannot write or read another account's row.

Re-submit is an idempotent UPSERT: a second POST updates the caller's existing row and
re-stamps `submitted_at` (the instrument is a personalization snapshot, not an immutable
record — see Story 6.3 Open Question #1). On success a `questionnaire_submitted` research
event is emitted via the non-blocking `research_logger`; emission NEVER crashes the request
(NFR22) — the durable record is the table row.
"""

import time

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.questionnaire_response import QuestionnaireResponse
from app.models.user import User
from app.schemas.questionnaire import (
    QuestionnaireResponseSchema,
    QuestionnaireSubmitRequest,
)
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


@router.post(
    "/onboarding/questionnaire",
    response_model=QuestionnaireResponseSchema,
    tags=["onboarding"],
)
async def submit_questionnaire(
    payload: QuestionnaireSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QuestionnaireResponse:
    """Persist (idempotent upsert) the caller's pre-study questionnaire answers.

    Writes ONLY the authenticated user's row; a `user_id` in the body is never trusted.
    Emits a non-blocking `questionnaire_submitted` research event (counts only, no raw PII).
    """
    result = await db.execute(
        select(QuestionnaireResponse).where(
            QuestionnaireResponse.user_id == current_user.id
        )
    )
    record = result.scalar_one_or_none()

    if record is None:
        record = QuestionnaireResponse(
            user_id=current_user.id, responses=payload.responses
        )
        db.add(record)
    else:
        record.responses = payload.responses
        record.submitted_at = func.now()

    await db.commit()
    await db.refresh(record)

    # Non-blocking research event — counts/section completion only, never raw PII.
    multi = payload.responses.get("Q9")
    await _safe_emit({
        "event_type": "questionnaire_submitted",
        "learner_id": str(current_user.id),
        "session_id": None,
        "cycle_number": 0,
        "timestamp": _now_ms(),
        "payload": {
            "user_id": str(current_user.id),
            "answered_count": len(payload.responses),
            "q9_selected_count": len(multi) if isinstance(multi, list) else 0,
        },
    })

    return record


@router.get(
    "/onboarding/questionnaire",
    response_model=QuestionnaireResponseSchema,
    tags=["onboarding"],
)
async def get_questionnaire(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QuestionnaireResponse:
    """Return the caller's own questionnaire submission, or 404 if none exists."""
    result = await db.execute(
        select(QuestionnaireResponse).where(
            QuestionnaireResponse.user_id == current_user.id
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "NOT_FOUND",
                    "message": "No questionnaire submission found",
                }
            },
        )
    return record
