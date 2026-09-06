from app.models.base import Base, BaseModel
from app.models.course import BlockType, ContentBlock, Course, Lesson, Module, Section
from app.models.content_version import ContentVersion
from app.models.decision_review import DecisionReview
from app.models.email_token import EmailToken
from app.models.assistance_event import AssistanceEvent
from app.models.enrollment import Enrollment
# `learner_profile` and `research_event` were missing from this list, which is the root cause of
# the `learner_profiles` table never existing: a model absent from `Base.metadata` is invisible to
# alembic autogenerate, so no migration was ever produced for it. Everything that reads the model
# registry — autogenerate, `create_all` in tests, the migration-coverage guard — needs every model
# imported here. Do not prune this list to "what is used".
from app.models.learner_profile import LearnerProfile
from app.models.research_event import ResearchEvent
from app.models.section_progress import SectionProgress
from app.models.assessment import (
    Assessment, AssessmentQuestion, AssessmentOption,
    AssessmentAttempt, QuestionResponse,
)
from app.models.questionnaire_response import QuestionnaireResponse
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_response import QuizBlockResponse
from app.models.section_visit import SectionVisit
from app.models.study_group import StudyGroup
from app.models.study_phase import StudyPhase
from app.models.system_config import SystemConfig
from app.models.survey_response import SurveyResponse
from app.models.user import Role, User

__all__ = [
    "Base", "BaseModel",
    "BlockType", "Course", "Module", "Lesson", "Section", "ContentBlock",
    "ContentVersion",
    "DecisionReview",
    "EmailToken",
    "AssistanceEvent",
    "Enrollment",
    "LearnerProfile",
    "ResearchEvent",
    "SectionProgress",
    "Assessment", "AssessmentQuestion", "AssessmentOption",
    "AssessmentAttempt", "QuestionResponse",
    "QuizAttempt",
    "QuizBlockResponse",
    "SectionVisit",
    "QuestionnaireResponse",
    "StudyGroup", "StudyPhase",
    "SystemConfig",
    "SurveyResponse",
    "Role", "User",
]
