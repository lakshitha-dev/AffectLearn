"""Assessment request/response schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, model_validator

from app.schemas.base import CamelModel


class AssessmentOptionCreate(CamelModel):
    text: str
    is_correct: bool
    sort_order: int


class AssessmentOptionResponse(CamelModel):
    id: uuid.UUID
    text: str
    sort_order: int
    model_config = ConfigDict(from_attributes=True)


class AssessmentOptionResult(CamelModel):
    id: uuid.UUID
    text: str
    sort_order: int
    is_correct: bool
    model_config = ConfigDict(from_attributes=True)


class AssessmentQuestionCreate(CamelModel):
    text: str
    sort_order: int
    explanation: str | None = None
    options: list[AssessmentOptionCreate]

    @model_validator(mode="after")
    def validate_single_correct_option(self) -> "AssessmentQuestionCreate":
        correct_count = sum(1 for o in self.options if o.is_correct)
        if correct_count != 1:
            raise ValueError("Exactly one option must be marked as correct")
        return self


class AssessmentQuestionResponse(CamelModel):
    id: uuid.UUID
    text: str
    sort_order: int
    options: list[AssessmentOptionResponse]
    model_config = ConfigDict(from_attributes=True)


class AssessmentQuestionDetailResponse(CamelModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    text: str
    sort_order: int
    explanation: str | None = None
    options: list[AssessmentOptionResponse]
    model_config = ConfigDict(from_attributes=True)


class AssessmentQuestionResult(CamelModel):
    id: uuid.UUID
    text: str
    sort_order: int
    explanation: str | None
    options: list[AssessmentOptionResult]
    selected_option_id: uuid.UUID | None
    is_correct: bool


class AssessmentCreate(CamelModel):
    module_id: uuid.UUID
    assessment_type: Literal["pre", "post"]
    title: str


class AssessmentResponse(CamelModel):
    id: uuid.UUID
    module_id: uuid.UUID
    assessment_type: Literal["pre", "post"]
    title: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AssessmentWithQuestionsResponse(AssessmentResponse):
    questions: list[AssessmentQuestionResponse]


class AnswerCreate(CamelModel):
    question_id: uuid.UUID
    selected_option_id: uuid.UUID


class AttemptCreate(CamelModel):
    answers: list[AnswerCreate]


class AttemptResponse(CamelModel):
    id: uuid.UUID
    score: int
    max_score: int
    submitted_at: datetime
    questions: list[AssessmentQuestionResult]
    pre_score: int | None = None
    pre_max_score: int | None = None
    model_config = ConfigDict(from_attributes=False)
