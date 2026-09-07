"""Post-study satisfaction survey API (Story 6.4).

`POST /surveys/satisfaction` persists the authenticated learner's end-of-study satisfaction
answers (the four AC dimensions) and `GET /surveys/satisfaction` returns the caller's own
submission (or 404 if none). Both endpoints require authentication and operate ONLY on the
caller's `user_id` — a `user_id` is NEVER read from the request body, so a learner cannot write
or read another account's row.

Re-submit is an idempotent UPSERT: a second POST updates the caller's existing row and re-stamps
`submitted_at`. On success a `survey_completed` research event is emitted via the non-blocking
`research_logger`; emission NEVER crashes the request (NFR22) — the durable record is the table
row. The >= 4.0/5 success target is a research metric only and is NOT enforced here (low scores
still persist and reach the Thank You page); the mean is computed for the event payload only.

This populates the EXISTING `surveys.py` stub already mounted at prefix `/surveys` in
`app/api/routes/__init__.py` (no re-mount).
"""

import time

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.models.survey_response import SurveyResponse
from app.models.user import Role, User
from app.schemas.survey import SurveyResponseSchema, SurveySubmitRequest
from app.services.research_logger import emit as emit_research_event

logger = structlog.get_logger(__name__)

# WHY THESE ARE LEARNER-ONLY
#
# These rows ARE the research dataset. On `get_current_user` any authenticated account — designer
# or admin — could submit one, and the resulting row is indistinguishable from a participant's
# after the fact, so a stray click while testing silently contaminates the study. The learner
# guard is the cheapest way to keep the dataset meaning what it claims to mean.

router = APIRouter()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _mean_score(responses: dict) -> float | None:
    """Compute the mean Likert score (1-5) for the research payload, or None if unusable.

    Research metric only (AC7) — never branches application behaviour, never asserted as a gate.
    """
    numeric: list[int] = []
    for v in responses.values():
        if isinstance(v, str) and v.isdigit():
            numeric.append(int(v))
    if not numeric:
        return None
    return round(sum(numeric) / len(numeric), 4)


async def _safe_emit(event: dict) -> None:
    """Emit a research event without ever propagating exceptions to the caller (NFR22)."""
    try:
        await emit_research_event(event)
    except Exception:
        logger.exception("research_event_emit_swallowed", event_type=event.get("event_type"))


@router.post(
    "/satisfaction",
    response_model=SurveyResponseSchema,
    tags=["surveys"],
)
async def submit_survey(
    payload: SurveySubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
) -> SurveyResponse:
    """Persist (idempotent upsert) the caller's post-study satisfaction answers.

    Writes ONLY the authenticated user's row; a `user_id` in the body is never trusted.
    Emits a non-blocking `survey_completed` research event (counts/mean only, no raw PII).
    """
    result = await db.execute(
        select(SurveyResponse).where(SurveyResponse.user_id == current_user.id)
    )
    record = result.scalar_one_or_none()

    if record is None:
        record = SurveyResponse(user_id=current_user.id, responses=payload.responses)
        db.add(record)
    else:
        record.responses = payload.responses
        record.submitted_at = func.now()

    await db.commit()
    await db.refresh(record)

    # Non-blocking research event — counts/mean only, never raw PII.
    await _safe_emit({
        "event_type": "survey_completed",
        "learner_id": str(current_user.id),
        "session_id": None,
        "cycle_number": 0,
        "timestamp": _now_ms(),
        "payload": {
            "user_id": str(current_user.id),
            "answered_count": len(payload.responses),
            "mean_score": _mean_score(payload.responses),
        },
    })

    return record


@router.get(
    "/satisfaction",
    response_model=SurveyResponseSchema,
    tags=["surveys"],
)
async def get_survey(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
) -> SurveyResponse:
    """Return the caller's own satisfaction survey submission, or 404 if none exists."""
    result = await db.execute(
        select(SurveyResponse).where(SurveyResponse.user_id == current_user.id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "NOT_FOUND",
                    "message": "No survey submission found",
                }
            },
        )
    return record
