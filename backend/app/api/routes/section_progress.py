"""Section progress and quiz response API endpoints."""

import uuid

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
from app.services import section_progress_service

router = APIRouter()


class QuizResponseCreate(CamelModel):
    content_block_id: uuid.UUID
    selected_answers: list[str]
    is_correct: bool


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
        db, user_id=current_user.id, section_id=body.section_id
    )
    response.status_code = (
        status.HTTP_201_CREATED if created else status.HTTP_200_OK
    )
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
    return record
