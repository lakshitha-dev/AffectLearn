"""Assessment API endpoints."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.models.user import Role, User
from app.schemas.assessment import (
    AssessmentCreate, AssessmentQuestionCreate, AssessmentQuestionDetailResponse,
    AssessmentResponse, AssessmentWithQuestionsResponse,
    AttemptCreate, AttemptResponse,
)
from app.services import assessment_service

router = APIRouter()


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
    return await assessment_service.submit_attempt(
        db,
        user_id=current_user.id,
        assessment_id=assessment_id,
        answers=body.answers,
    )