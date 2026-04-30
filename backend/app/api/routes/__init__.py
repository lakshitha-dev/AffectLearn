from fastapi import APIRouter

from app.api.routes import (
    admin,
    analytics,
    assessments,
    auth,
    courses,
    enrollments,
    learners,
    surveys,
    ws,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(courses.router, prefix="/courses", tags=["courses"])
api_router.include_router(enrollments.router, prefix="/enrollments", tags=["enrollments"])
api_router.include_router(learners.router, prefix="/learners", tags=["learners"])
api_router.include_router(assessments.router, prefix="/assessments", tags=["assessments"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(surveys.router, prefix="/surveys", tags=["surveys"])
api_router.include_router(ws.router, prefix="/ws", tags=["websocket"])
