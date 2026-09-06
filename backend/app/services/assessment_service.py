"""Async service functions for assessments."""

import random
import uuid
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.assessment import (
    Assessment, AssessmentAttempt, AssessmentOption,
    AssessmentQuestion, QuestionResponse,
)
from app.models.course import Lesson, Module, Section
from app.models.enrollment import Enrollment
from app.models.section_progress import SectionProgress
from app.schemas.assessment import (
    AnswerCreate, AssessmentCreate, AssessmentOptionResult,
    AssessmentQuestionCreate, AssessmentQuestionResult,
    AssessmentWithQuestionsResponse, AssessmentOptionResponse,
    AssessmentQuestionResponse, AttemptResponse,
)


async def _get_assessment_or_404(db: AsyncSession, assessment_id: uuid.UUID) -> Assessment:
    stmt = (
        select(Assessment)
        .where(Assessment.id == assessment_id)
        .options(
            selectinload(Assessment.questions).selectinload(AssessmentQuestion.options)
        )
    )
    assessment = (await db.execute(stmt)).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "ASSESSMENT_NOT_FOUND", "message": "Assessment not found"}},
        )
    return assessment


async def _verify_enrollment(db: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID) -> Enrollment:
    enrollment = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.user_id == user_id,
                Enrollment.course_id == course_id,
            )
        )
    ).scalar_one_or_none()
    if enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "NOT_ENROLLED", "message": "Not enrolled in this course"}},
        )
    return enrollment


async def _get_course_id_for_module(db: AsyncSession, module_id: uuid.UUID) -> uuid.UUID:
    module = (await db.execute(select(Module).where(Module.id == module_id))).scalar_one_or_none()
    if module is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Module not found"}})
    return module.course_id


async def get_assessment_detail(db: AsyncSession, assessment_id: uuid.UUID) -> Assessment:
    """Public wrapper around _get_assessment_or_404 for use by route handlers."""
    return await _get_assessment_or_404(db, assessment_id)


async def create_assessment(db: AsyncSession, *, data: AssessmentCreate) -> Assessment:
    assessment = Assessment(
        module_id=data.module_id,
        assessment_type=data.assessment_type,
        title=data.title,
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return assessment


async def add_question(
    db: AsyncSession, *, assessment_id: uuid.UUID, data: AssessmentQuestionCreate
) -> AssessmentQuestion:
    await _get_assessment_or_404(db, assessment_id)
    question = AssessmentQuestion(
        assessment_id=assessment_id,
        text=data.text,
        sort_order=data.sort_order,
        explanation=data.explanation,
    )
    db.add(question)
    await db.flush()
    for opt_data in data.options:
        db.add(AssessmentOption(
            question_id=question.id,
            text=opt_data.text,
            is_correct=opt_data.is_correct,
            sort_order=opt_data.sort_order,
        ))
    await db.commit()
    # Reload with options eagerly loaded
    stmt = (
        select(AssessmentQuestion)
        .where(AssessmentQuestion.id == question.id)
        .options(selectinload(AssessmentQuestion.options))
    )
    question = (await db.execute(stmt)).scalar_one()
    return question


async def get_assessment_by_module(
    db: AsyncSession,
    *,
    module_id: uuid.UUID,
    assessment_type: Literal["pre", "post"],
) -> Assessment | None:
    stmt = select(Assessment).where(
        Assessment.module_id == module_id,
        Assessment.assessment_type == assessment_type,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_assessment_for_learner(
    db: AsyncSession,
    *,
    assessment_id: uuid.UUID,
    user_id: uuid.UUID,
) -> AssessmentWithQuestionsResponse:
    assessment = await _get_assessment_or_404(db, assessment_id)
    course_id = await _get_course_id_for_module(db, assessment.module_id)
    await _verify_enrollment(db, user_id, course_id)

    questions_resp = []
    for q in sorted(assessment.questions, key=lambda x: x.sort_order):
        options = list(q.options)
        random.shuffle(options)
        questions_resp.append(AssessmentQuestionResponse(
            id=q.id,
            text=q.text,
            sort_order=q.sort_order,
            options=[AssessmentOptionResponse(id=o.id, text=o.text, sort_order=o.sort_order) for o in options],
        ))

    return AssessmentWithQuestionsResponse(
        id=assessment.id,
        module_id=assessment.module_id,
        assessment_type=assessment.assessment_type,
        title=assessment.title,
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
        questions=questions_resp,
    )


async def has_submitted_attempt(db: AsyncSession, *, user_id: uuid.UUID, assessment_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(AssessmentAttempt.id).where(
            AssessmentAttempt.user_id == user_id,
            AssessmentAttempt.assessment_id == assessment_id,
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def check_module_complete(db: AsyncSession, *, user_id: uuid.UUID, module_id: uuid.UUID) -> bool:
    total_stmt = (
        select(func.count(Section.id))
        .join(Lesson, Section.lesson_id == Lesson.id)
        .where(Lesson.module_id == module_id)
    )
    total = (await db.execute(total_stmt)).scalar_one()
    if total == 0:
        return True

    completed_stmt = (
        select(func.count(SectionProgress.id))
        .join(Section, SectionProgress.section_id == Section.id)
        .join(Lesson, Section.lesson_id == Lesson.id)
        .where(Lesson.module_id == module_id, SectionProgress.user_id == user_id)
    )
    completed = (await db.execute(completed_stmt)).scalar_one()
    return completed >= total


async def get_latest_attempt(
    db: AsyncSession, *, user_id: uuid.UUID, assessment_id: uuid.UUID
) -> AssessmentAttempt | None:
    stmt = (
        select(AssessmentAttempt)
        .where(
            AssessmentAttempt.user_id == user_id,
            AssessmentAttempt.assessment_id == assessment_id,
        )
        .options(selectinload(AssessmentAttempt.responses))
        .order_by(AssessmentAttempt.submitted_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def build_attempt_response(
    db: AsyncSession, attempt: AssessmentAttempt, assessment: Assessment,
    pre_score: int | None = None, pre_max_score: int | None = None,
) -> AttemptResponse:
    response_map = {r.question_id: r for r in attempt.responses}
    questions_result = []
    for q in sorted(assessment.questions, key=lambda x: x.sort_order):
        resp = response_map.get(q.id)
        options_result = [
            AssessmentOptionResult(id=o.id, text=o.text, sort_order=o.sort_order, is_correct=o.is_correct)
            for o in q.options
        ]
        questions_result.append(AssessmentQuestionResult(
            id=q.id,
            text=q.text,
            sort_order=q.sort_order,
            explanation=q.explanation,
            options=options_result,
            selected_option_id=resp.selected_option_id if resp else None,
            is_correct=resp.is_correct if resp else False,
        ))
    return AttemptResponse(
        id=attempt.id,
        score=attempt.score,
        max_score=attempt.max_score,
        submitted_at=attempt.submitted_at,
        questions=questions_result,
        pre_score=pre_score,
        pre_max_score=pre_max_score,
    )


async def submit_attempt(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    assessment_id: uuid.UUID,
    answers: list[AnswerCreate],
    started_at: Any = None,
) -> AttemptResponse:
    assessment = await _get_assessment_or_404(db, assessment_id)
    course_id = await _get_course_id_for_module(db, assessment.module_id)
    enrollment = await _verify_enrollment(db, user_id, course_id)

    if assessment.assessment_type == "post":
        if not await check_module_complete(db, user_id=user_id, module_id=assessment.module_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "MODULE_NOT_COMPLETE", "message": "Complete all module sections before taking the post-assessment"}},
            )

    question_ids = {q.id for q in assessment.questions}
    answered_ids = {a.question_id for a in answers}
    if answered_ids != question_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "INCOMPLETE_ANSWERS", "message": "All questions must be answered"}},
        )

    option_map: dict[uuid.UUID, AssessmentOption] = {}
    for q in assessment.questions:
        for o in q.options:
            option_map[o.id] = o

    score = 0
    # Migration 022. `api/routes/assessments.py` has always emitted this ordinal on the
    # `exercise_attempted` research event, reading it with a getattr default of 0 -- and nothing
    # ever assigned it, so every event recorded a constant zero. A pre/post design turns on
    # knowing which attempt a score belongs to, so counting it here is a data fix, not a feature.
    prior_attempts = (
        await db.execute(
            select(func.count(AssessmentAttempt.id)).where(
                AssessmentAttempt.user_id == user_id,
                AssessmentAttempt.assessment_id == assessment_id,
            )
        )
    ).scalar_one()
    attempt = AssessmentAttempt(
        user_id=user_id,
        assessment_id=assessment_id,
        enrollment_id=enrollment.id,
        score=0,
        max_score=len(assessment.questions),
        attempt_number=int(prior_attempts or 0) + 1,
        started_at=started_at,
    )
    db.add(attempt)
    await db.flush()

    responses = []
    for ans in answers:
        option = option_map.get(ans.selected_option_id)
        correct = option.is_correct if option else False
        if correct:
            score += 1
        resp = QuestionResponse(
            attempt_id=attempt.id,
            question_id=ans.question_id,
            selected_option_id=ans.selected_option_id,
            is_correct=correct,
        )
        db.add(resp)
        responses.append(resp)

    attempt.score = score
    await db.commit()
    # Reload with responses eagerly loaded
    stmt = (
        select(AssessmentAttempt)
        .where(AssessmentAttempt.id == attempt.id)
        .options(selectinload(AssessmentAttempt.responses))
    )
    attempt = (await db.execute(stmt)).scalar_one()

    pre_score = pre_max = None
    if assessment.assessment_type == "post":
        pre_assessment = await get_assessment_by_module(db, module_id=assessment.module_id, assessment_type="pre")
        if pre_assessment:
            pre_attempt = await get_latest_attempt(db, user_id=user_id, assessment_id=pre_assessment.id)
            if pre_attempt:
                pre_score = pre_attempt.score
                pre_max = pre_attempt.max_score

    return await build_attempt_response(db, attempt, assessment, pre_score=pre_score, pre_max_score=pre_max)