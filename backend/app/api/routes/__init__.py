from fastapi import APIRouter

from app.api.routes import (
    admin,
    analytics,
    assessments,
    auth,
    courses,
    enrollments,
    learner_profiles,
    learners,
    monitor,
    questionnaire,
    research,
    reviews,
    section_progress,
    study,
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
# No prefix: the paths are declared in full on the router, matching `research.py`.
api_router.include_router(reviews.router)
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(study.router, prefix="/admin", tags=["study"])
api_router.include_router(research.router, prefix="/admin", tags=["research"])
api_router.include_router(surveys.router, prefix="/surveys", tags=["surveys"])
api_router.include_router(questionnaire.router, tags=["onboarding"])
api_router.include_router(section_progress.router)
api_router.include_router(learner_profiles.router, tags=["learner-profiles"])
api_router.include_router(ws.router, prefix="/ws", tags=["websocket"])
api_router.include_router(monitor.router, prefix="/monitor", tags=["monitor"])
