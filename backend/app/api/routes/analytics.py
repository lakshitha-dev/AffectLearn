"""Analytics API endpoints."""

from fastapi import APIRouter, Depends

from app.core.deps import require_role
from app.models.user import Role, User
from app.schemas.analytics import CourseAnalyticsResponse

router = APIRouter()


@router.get("/courses", response_model=list[CourseAnalyticsResponse])
async def list_course_analytics(
    current_user: User = Depends(require_role(Role.course_designer, Role.admin)),
):
    """Placeholder course analytics. Requires course_designer or admin role."""
    return [
        CourseAnalyticsResponse(
            course_id="placeholder-1",
            title="Introduction to Adaptive Learning",
            enrollment_count=0,
            completion_rate=0.0,
        ),
    ]
