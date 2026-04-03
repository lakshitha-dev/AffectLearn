"""Analytics response schemas."""

from app.schemas.base import CamelModel


class CourseAnalyticsResponse(CamelModel):
    course_id: str
    title: str
    enrollment_count: int
    completion_rate: float
