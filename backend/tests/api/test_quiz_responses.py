"""Tests for the quiz-response recording endpoint.

Route: POST /api/v1/quiz-responses
Schema (camelCase over the wire):
  { contentBlockId, selectedAnswers: list[str], isCorrect: bool }

The endpoint is an idempotent upsert:
  - First call  -> 201 Created
  - Repeat call -> 200 OK (returns the existing record unchanged)
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import BlockType, ContentBlock

QUIZ_RESPONSES_URL = "/api/v1/quiz-responses"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_content_block(
    db: AsyncSession,
    section_id,
    *,
    block_type: BlockType = BlockType.quiz,
    sort_order: int = 0,
    content: dict | None = None,
) -> ContentBlock:
    """Insert a ContentBlock into the DB and return the refreshed instance."""
    if content is None:
        content = {
            "quizType": "single",
            "question": "What is 2+2?",
            "options": [
                {"id": "opt-a", "text": "3", "isCorrect": False},
                {"id": "opt-b", "text": "4", "isCorrect": True},
            ],
            "explanation": "2+2=4",
        }
    block = ContentBlock(
        section_id=section_id,
        block_type=block_type,
        sort_order=sort_order,
        variant_key="original",
        variant_group=uuid.uuid4(),
        content=content,
    )
    db.add(block)
    await db.commit()
    await db.refresh(block)
    return block


# ---------------------------------------------------------------------------
# POST /quiz-responses — happy paths
# ---------------------------------------------------------------------------


class TestRecordQuizResponse:

    async def test_first_submission_returns_201(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """First POST for a block returns HTTP 201 Created."""
        section = enrolled_course["sections"][0]
        block = await _create_content_block(db, section.id)

        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(block.id),
                "selectedAnswers": ["opt-b"],
                "isCorrect": True,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201

    async def test_response_body_contains_expected_fields(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """Response includes id, contentBlockId, and isCorrect."""
        section = enrolled_course["sections"][0]
        block = await _create_content_block(db, section.id)

        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(block.id),
                "selectedAnswers": ["opt-b"],
                "isCorrect": True,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["contentBlockId"] == str(block.id)
        assert data["isCorrect"] is True

    async def test_correct_answer_stored(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """When isCorrect=True the persisted record reflects that."""
        section = enrolled_course["sections"][0]
        block = await _create_content_block(db, section.id)

        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(block.id),
                "selectedAnswers": ["opt-b"],
                "isCorrect": True,
            },
            headers=auth_headers,
        )
        assert resp.json()["isCorrect"] is True

    async def test_incorrect_answer_stored(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """When isCorrect=False the persisted record reflects that."""
        section = enrolled_course["sections"][0]
        block = await _create_content_block(db, section.id)

        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(block.id),
                "selectedAnswers": ["opt-a"],
                "isCorrect": False,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["isCorrect"] is False

    async def test_multiple_selected_answers_accepted(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """Multiple-choice answers (multiple ids in selectedAnswers) are stored."""
        section = enrolled_course["sections"][0]
        multi_content = {
            "quizType": "multiple",
            "question": "Which are even?",
            "options": [
                {"id": "opt-1", "text": "2", "isCorrect": True},
                {"id": "opt-2", "text": "3", "isCorrect": False},
                {"id": "opt-3", "text": "4", "isCorrect": True},
            ],
            "explanation": "2 and 4 are even.",
        }
        block = await _create_content_block(
            db, section.id, sort_order=0, content=multi_content
        )

        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(block.id),
                "selectedAnswers": ["opt-1", "opt-3"],
                "isCorrect": True,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["isCorrect"] is True

    async def test_exercise_block_submission_accepted(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """Exercise (text_input) blocks can be submitted the same way."""
        section = enrolled_course["sections"][0]
        exercise_content = {
            "exerciseType": "text_input",
            "prompt": "Type the number four.",
            "correctAnswer": "four",
            "explanation": "The word is 'four'.",
        }
        block = await _create_content_block(
            db,
            section.id,
            block_type=BlockType.exercise,
            sort_order=0,
            content=exercise_content,
        )

        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(block.id),
                "selectedAnswers": [],
                "isCorrect": True,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["isCorrect"] is True

    async def test_empty_selected_answers_accepted(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """An empty selectedAnswers list (e.g. for exercises) is valid."""
        section = enrolled_course["sections"][0]
        block = await _create_content_block(db, section.id)

        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(block.id),
                "selectedAnswers": [],
                "isCorrect": False,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# POST /quiz-responses — idempotency
# ---------------------------------------------------------------------------


class TestRecordQuizResponseIdempotency:

    async def test_repeat_submission_returns_200(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """Second POST for the same block returns HTTP 200 OK."""
        section = enrolled_course["sections"][0]
        block = await _create_content_block(db, section.id)
        payload = {
            "contentBlockId": str(block.id),
            "selectedAnswers": ["opt-b"],
            "isCorrect": True,
        }
        await client.post(QUIZ_RESPONSES_URL, json=payload, headers=auth_headers)
        resp = await client.post(QUIZ_RESPONSES_URL, json=payload, headers=auth_headers)
        assert resp.status_code == 200

    async def test_repeat_submission_returns_same_record(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """Both calls return the same record id."""
        section = enrolled_course["sections"][0]
        block = await _create_content_block(db, section.id)
        payload = {
            "contentBlockId": str(block.id),
            "selectedAnswers": ["opt-b"],
            "isCorrect": True,
        }
        r1 = await client.post(QUIZ_RESPONSES_URL, json=payload, headers=auth_headers)
        r2 = await client.post(QUIZ_RESPONSES_URL, json=payload, headers=auth_headers)
        assert r1.json()["id"] == r2.json()["id"]

    async def test_different_blocks_each_get_own_record(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """Submitting responses for two different blocks creates two distinct records."""
        section = enrolled_course["sections"][0]
        block_a = await _create_content_block(db, section.id, sort_order=0)
        block_b = await _create_content_block(
            db,
            section.id,
            sort_order=1,
            content={
                "quizType": "single",
                "question": "What is 3+3?",
                "options": [
                    {"id": "opt-x", "text": "5", "isCorrect": False},
                    {"id": "opt-y", "text": "6", "isCorrect": True},
                ],
                "explanation": "3+3=6",
            },
        )

        r_a = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(block_a.id),
                "selectedAnswers": ["opt-b"],
                "isCorrect": True,
            },
            headers=auth_headers,
        )
        r_b = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(block_b.id),
                "selectedAnswers": ["opt-y"],
                "isCorrect": True,
            },
            headers=auth_headers,
        )
        assert r_a.status_code == 201
        assert r_b.status_code == 201
        assert r_a.json()["id"] != r_b.json()["id"]


# ---------------------------------------------------------------------------
# POST /quiz-responses — validation errors
# ---------------------------------------------------------------------------


class TestRecordQuizResponseValidation:

    async def test_missing_content_block_id_returns_422(
        self, client: AsyncClient, auth_headers
    ):
        """Request without contentBlockId must be rejected."""
        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={"selectedAnswers": ["opt-b"], "isCorrect": True},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_missing_selected_answers_returns_422(
        self, client: AsyncClient, auth_headers
    ):
        """Request without selectedAnswers must be rejected."""
        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={"contentBlockId": str(uuid.uuid4()), "isCorrect": True},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_missing_is_correct_returns_422(
        self, client: AsyncClient, auth_headers
    ):
        """Request without isCorrect must be rejected."""
        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(uuid.uuid4()),
                "selectedAnswers": ["opt-b"],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_invalid_uuid_for_content_block_id_returns_422(
        self, client: AsyncClient, auth_headers
    ):
        """A non-UUID string for contentBlockId must be rejected."""
        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": "not-a-uuid",
                "selectedAnswers": [],
                "isCorrect": False,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /quiz-responses — RBAC / authentication
# ---------------------------------------------------------------------------


class TestRecordQuizResponseRBAC:

    async def test_designer_cannot_submit_quiz_response(
        self, client: AsyncClient, enrolled_course, designer_headers, db: AsyncSession
    ):
        """Course designers are not learners and must receive 403."""
        section = enrolled_course["sections"][0]
        block = await _create_content_block(db, section.id)

        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(block.id),
                "selectedAnswers": ["opt-b"],
                "isCorrect": True,
            },
            headers=designer_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"]["code"] == "FORBIDDEN"

    async def test_admin_cannot_submit_quiz_response(
        self, client: AsyncClient, enrolled_course, admin_headers, db: AsyncSession
    ):
        """Admins are not learners and must receive 403."""
        section = enrolled_course["sections"][0]
        block = await _create_content_block(db, section.id)

        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(block.id),
                "selectedAnswers": ["opt-b"],
                "isCorrect": True,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"]["code"] == "FORBIDDEN"

    async def test_unauthenticated_returns_401_or_403(
        self, client: AsyncClient, enrolled_course, db: AsyncSession
    ):
        """No auth token must be rejected."""
        section = enrolled_course["sections"][0]
        block = await _create_content_block(db, section.id)

        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(block.id),
                "selectedAnswers": ["opt-b"],
                "isCorrect": True,
            },
        )
        assert resp.status_code in (401, 403)


class TestEnrollmentIsRequired:
    """Answering a quiz for a course you never joined used to be accepted.

    `mark_section_complete` has always refused this; recording an ANSWER did not. Both
    `quiz_responses` and `quiz_attempts` feed the "quizzes answered / correct" figures in
    `progress_service` and the research export, so an unenrolled write moves reported accuracy
    rather than sitting harmlessly in a table.
    """

    async def test_unenrolled_learner_is_refused(
        self, client: AsyncClient, db: AsyncSession, auth_headers
    ):
        from app.models.course import Course, Lesson, Module, Section

        # A course the learner is NOT enrolled in.
        course = Course(title="Someone Else's Course", is_published=True)
        db.add(course)
        await db.flush()
        module = Module(title="M", sort_order=0, course_id=course.id)
        db.add(module)
        await db.flush()
        lesson = Lesson(title="L", sort_order=0, module_id=module.id)
        db.add(lesson)
        await db.flush()
        section = Section(title="S", sort_order=0, lesson_id=lesson.id)
        db.add(section)
        await db.flush()
        block = ContentBlock(
            block_type=BlockType.quiz,
            content={"question": "?", "options": []},
            sort_order=0,
            section_id=section.id,
        )
        db.add(block)
        await db.commit()
        await db.refresh(block)

        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(block.id),
                "selectedAnswers": ["a"],
                "isCorrect": True,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"]["code"] == "NOT_ENROLLED"

    async def test_unknown_block_is_404(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(uuid.uuid4()),
                "selectedAnswers": ["a"],
                "isCorrect": True,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_the_guard_cannot_be_skipped_by_omitting_section_id(
        self, client: AsyncClient, db: AsyncSession, auth_headers, enrolled_course
    ):
        """`sectionId` is optional on the wire, so the check resolves from the BLOCK instead.

        Resolving from a field the client may omit would be a guard the client can turn off.
        """
        section = enrolled_course["sections"][0]
        block = await _create_content_block(db, section.id)

        resp = await client.post(
            QUIZ_RESPONSES_URL,
            json={
                "contentBlockId": str(block.id),
                "selectedAnswers": ["a"],
                "isCorrect": True,
            },  # no sectionId
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201)
