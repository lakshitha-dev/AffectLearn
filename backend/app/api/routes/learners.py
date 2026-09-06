"""Learner-scoped reads.

This module was an empty `APIRouter()` — three lines, mounted at `/api/v1/learners`, exposing
nothing. It now serves the learner's own help history, which is the read
`assistance_service.for_learner` was written for ("The read behind a learner-facing hint history")
and which had no route.

WHAT IS DELIBERATELY NOT RETURNED

No affect state, no confidence, no gate reason. `architecture.md` lists "showing detected affect
state to learners" as an anti-pattern — that data belongs on the designer analytics dashboard, and
telling a learner the system decided they looked confused changes the behaviour the system is
trying to measure. What comes back is what the learner already saw on screen: the help itself,
where it appeared, and what they did with it.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.models.user import Role, User
from app.schemas.base import CamelModel
from app.services import assistance_service

router = APIRouter()


class AssistanceHistoryItem(CamelModel):
    """One piece of help the learner was shown."""

    id: uuid.UUID
    created_at: datetime
    #: `show_hint`, `show_alternative`, `suggest_break`, …
    action_type: str | None = None
    #: The text as it appeared on screen.
    hint_text: str | None = None
    section_id: uuid.UUID | None = None
    course_id: uuid.UUID | None = None
    #: What the learner did with it: `accepted`, `dismissed`, … or None if they did nothing.
    interaction: str | None = None
    #: Whether the next attempt after this help was correct. None when there was no next attempt,
    #: which is not the same as "no" and must not be collapsed into it.
    outcome_is_correct: bool | None = None


@router.get("/me/assistance", response_model=list[AssistanceHistoryItem])
async def my_assistance_history(
    limit: int = Query(default=50, ge=1, le=200),
    course_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    """The help this learner has been shown, newest first.

    Scoped to the caller by construction — there is no path parameter to point at somebody else.
    """
    events = await assistance_service.for_learner(
        db, learner_id=current_user.id, limit=limit, course_id=course_id
    )
    return [
        AssistanceHistoryItem(
            id=event.id,
            created_at=event.created_at,
            action_type=event.action_type,
            hint_text=event.hint_text,
            section_id=event.section_id,
            course_id=event.course_id,
            interaction=event.interaction,
            outcome_is_correct=event.outcome_is_correct,
        )
        for event in events
    ]
