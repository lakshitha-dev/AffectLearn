"""Correctness is graded on the server from the block's answer key (quiz and exercise).

The learning outcome the between-group comparison rests on used to be whatever the browser sent.
These tests pin that the stored verdict is the server's, that disagreement is recorded rather than
hidden, and that exercise answers -- submitted for the first time -- do not move the "quizzes
answered / correct" figures that count `quiz_responses`.
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.section_progress import grade_answer
from app.models.course import BlockType, ContentBlock
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_response import QuizBlockResponse

URL = "/api/v1/quiz-responses"

QUIZ = {
    "quizType": "single", "question": "2+2?",
    "options": [{"id": "a", "text": "3", "isCorrect": False},
                {"id": "b", "text": "4", "isCorrect": True}],
}
MULTI = {
    "quizType": "multiple", "question": "Even numbers?",
    "options": [{"id": "a", "text": "2", "isCorrect": True},
                {"id": "b", "text": "3", "isCorrect": False},
                {"id": "c", "text": "4", "isCorrect": True}],
}
EXERCISE = {"prompt": "Name the loop", "answer": "ReAct", "type": "text"}
REFLECTION = {"prompt": "What surprised you?", "answer": "", "type": "text"}


async def _block(db: AsyncSession, section_id, block_type, content) -> ContentBlock:
    block = ContentBlock(section_id=section_id, block_type=block_type, sort_order=0,
                         variant_key="original", variant_group=uuid.uuid4(), content=content)
    db.add(block)
    await db.commit()
    await db.refresh(block)
    return block


class TestGradeAnswer:
    def test_single_choice(self):
        assert grade_answer("quiz", QUIZ, ["b"]) is True
        assert grade_answer("quiz", QUIZ, ["a"]) is False

    def test_multiple_choice_needs_exactly_the_correct_set(self):
        assert grade_answer("quiz", MULTI, ["a", "c"]) is True
        assert grade_answer("quiz", MULTI, ["a"]) is False
        assert grade_answer("quiz", MULTI, ["a", "b", "c"]) is False

    def test_exercise_matches_the_client_rule(self):
        assert grade_answer("exercise", EXERCISE, ["  react "]) is True
        assert grade_answer("exercise", EXERCISE, ["chain"]) is False

    def test_no_answer_key_means_no_server_grade(self):
        assert grade_answer("exercise", REFLECTION, ["anything"]) is None
        assert grade_answer("quiz", {"options": []}, ["a"]) is None
        assert grade_answer("text", {}, []) is None


class TestServerGrading:
    async def test_a_wrong_answer_claimed_correct_is_stored_as_wrong(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        block = await _block(db, enrolled_course["sections"][0].id, BlockType.quiz, QUIZ)
        resp = await client.post(URL, headers=auth_headers, json={
            "contentBlockId": str(block.id), "selectedAnswers": ["a"], "isCorrect": True,
        })
        assert resp.status_code == 201
        assert resp.json()["isCorrect"] is False
        summary = (await db.execute(select(QuizBlockResponse))).scalar_one()
        attempt = (await db.execute(select(QuizAttempt))).scalar_one()
        assert summary.is_correct is False and attempt.is_correct is False

    async def test_an_exercise_answer_is_graded_and_kept_out_of_the_quiz_summary(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        block = await _block(db, enrolled_course["sections"][0].id, BlockType.exercise, EXERCISE)
        resp = await client.post(URL, headers=auth_headers, json={
            "contentBlockId": str(block.id), "selectedAnswers": ["react"], "isCorrect": False,
            "responseTimeMs": 4200,
        })
        assert resp.status_code == 201
        assert resp.json()["isCorrect"] is True
        assert (await db.execute(select(func.count(QuizBlockResponse.id)))).scalar_one() == 0
        attempt = (await db.execute(select(QuizAttempt))).scalar_one()
        assert attempt.is_correct is True and attempt.response_time_ms == 4200

    async def test_a_reflection_keeps_the_client_value(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        block = await _block(db, enrolled_course["sections"][0].id, BlockType.exercise, REFLECTION)
        resp = await client.post(URL, headers=auth_headers, json={
            "contentBlockId": str(block.id), "selectedAnswers": ["thoughts"], "isCorrect": False,
        })
        assert resp.status_code == 201
        assert resp.json()["isCorrect"] is False

    async def test_the_research_event_says_who_graded(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession, monkeypatch
    ):
        import app.api.routes.section_progress as routes

        events: list[dict] = []

        async def capture(event):
            events.append(event)

        monkeypatch.setattr(routes, "_safe_emit", capture)
        block = await _block(db, enrolled_course["sections"][0].id, BlockType.quiz, QUIZ)
        await client.post(URL, headers=auth_headers, json={
            "contentBlockId": str(block.id), "selectedAnswers": ["a"], "isCorrect": True,
        })
        payload = next(e for e in events if e["event_type"] == "quiz_submitted")["payload"]
        assert payload["is_correct"] is False
        assert payload["graded_by"] == "server"
        assert payload["client_is_correct"] is True
        assert payload["block_type"] == "quiz"

