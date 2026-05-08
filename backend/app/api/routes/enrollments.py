"""Course enrollment API endpoints."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_role
from app.models.user import Role, User
from app.schemas.enrollment import (
    EnrollmentCreate,
    EnrollmentDetailResponse,
    EnrollmentListResponse,
    EnrollmentResponse,
)
from app.schemas.section_progress import ResumeTargetResponse
from app.services import enrollment_service, section_progress_service

router = APIRouter()


def _enrollment_to_detail(
    enrollment, course, module_count: int
) -> EnrollmentDetailResponse:
    return EnrollmentDetailResponse(
        id=enrollment.id,
        user_id=enrollment.user_id,
        course_id=enrollment.course_id,
        enrolled_at=enrollment.enrolled_at,
        progress_percentage=enrollment.progress_percentage,
        last_accessed_at=enrollment.last_accessed_at,
        status=enrollment.status,
        created_at=enrollment.created_at,
        updated_at=enrollment.updated_at,
        course_title=course.title,
        course_description=course.description,
        course_estimated_duration_minutes=course.estimated_duration_minutes,
        course_module_count=module_count,
    )


@router.post("", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
async def create_enrollment(
    body: EnrollmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    return await enrollment_service.create_enrollment(
        db, user_id=current_user.id, course_id=body.course_id
    )


@router.get("", response_model=EnrollmentListResponse)
async def list_enrollments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    rows, total = await enrollment_service.list_user_enrollments(
        db, user_id=current_user.id, page=page, page_size=page_size
    )
    items = [_enrollment_to_detail(e, c, mc) for e, c, mc in rows]
    return EnrollmentListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{course_id}/resume", response_model=ResumeTargetResponse)
async def get_resume_target(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    """Return the first incomplete section for the learner in a course."""
    data = await section_progress_service.compute_resume_target(
        db, user_id=current_user.id, course_id=course_id
    )
    return ResumeTargetResponse(**data)


@router.get("/{course_id}", response_model=EnrollmentResponse | None)
async def get_enrollment_status(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the caller's enrollment for `course_id`, or null if not enrolled."""
    enrollment = await enrollment_service.get_enrollment(
        db, user_id=current_user.id, course_id=course_id
    )
    return enrollment
