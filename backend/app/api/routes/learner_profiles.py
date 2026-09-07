"""Learner profile / progress API endpoints (Story 4.6)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import Role, User
from app.schemas.progress import LearnerProgressResponse
from app.services import progress_service

router = APIRouter()


@router.get(
    "/learner-profiles/{learner_id}/progress",
    response_model=LearnerProgressResponse,
    tags=["learner-profiles"],
)
async def get_learner_progress(
    learner_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregated progress for a learner (completion %, section history, quiz scores).

    A learner may read only their own progress; admins may read any.
    An unknown learner_id yields empty aggregates rather than an error.

    WHY DESIGNERS ARE NOT ALLOWED HERE

    This aggregate spans EVERY course the learner is enrolled in, so handing it to a course
    designer would show them that learner's progress through other designers' courses as well —
    a cross-course leak that no designer screen ever asked for. Both callers of this endpoint
    (`/progress` and the study thank-you summary) read the caller's OWN progress.

    A designer's legitimate need is the roster for a course they own, which is course-scoped by
    construction and belongs on its own endpoint rather than by widening this one.
    """
    if current_user.role != Role.admin and current_user.id != learner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": "Cannot view another learner's progress"}},
        )
    return await progress_service.get_learner_progress(db, learner_id)
