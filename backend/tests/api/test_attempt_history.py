"""Attempt history: every submission is kept, not only the first (migration 022).

`quiz_responses` is UNIQUE(user_id, content_block_id) and its route returns the existing row on a
repeat, so the FIRST answer wins and every later one was discarded. A learner who answered
wrongly, received a hint, and then answered correctly left a durable record saying only "wrong".

These tests pin both halves of the fix: the summary keeps its old meaning (so `progress_service`
counts what it always counted), and the history keeps everything the summary throws away.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import BlockType, ContentBlock
from app.models.quiz_attempt import QuizAttempt
from app.models.quiz_response import QuizBlockResponse
from app.models.section_visit import SectionVisit

QUIZ_URL = "/api/v1/quiz-responses"
VISITS_URL = "/api/v1/section-visits"

pytestmark = pytest.mark.asyncio


async def _block(db: AsyncSession, section_id, sort_order: int = 0) -> ContentBlock:
    block = ContentBlock(
        section_id=section_id,
        block_type=BlockType.quiz,
        sort_order=sort_order,
        variant_key="original",
        variant_group=uuid.uuid4(),
        content={"quizType": "single", "question": "2+2?", "options": []},
    )
    db.add(block)
    await db.commit()
    await db.refresh(block)
    return block


async def _attempts(db: AsyncSession, block_id) -> list[QuizAttempt]:
    rows = (
        await db.execute(
            select(QuizAttempt)
            .where(QuizAttempt.content_block_id == block_id)
            .order_by(QuizAttempt.attempt_number)
        )
    ).scalars().all()
    return list(rows)


class TestQuizAttemptHistory:

    async def test_first_submission_records_attempt_one(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        block = await _block(db, enrolled_course["sections"][0].id)
        resp = await client.post(
            QUIZ_URL,
            json={"contentBlockId": str(block.id), "selectedAnswers": ["a"], "isCorrect": False},
            headers=auth_headers,
        )
        assert resp.status_code == 201

        attempts = await _attempts(db, block.id)
        assert len(attempts) == 1
        assert attempts[0].attempt_number == 1
        assert attempts[0].is_correct is False

    async def test_wrong_then_right_keeps_both(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """The case the old schema erased, and the one that makes "did the help work" askable."""
        block = await _block(db, enrolled_course["sections"][0].id)
        await client.post(
            QUIZ_URL,
            json={"contentBlockId": str(block.id), "selectedAnswers": ["a"], "isCorrect": False},
            headers=auth_headers,
        )
        await client.post(
            QUIZ_URL,
            json={"contentBlockId": str(block.id), "selectedAnswers": ["b"], "isCorrect": True},
            headers=auth_headers,
        )

        attempts = await _attempts(db, block.id)
        assert [(a.attempt_number, a.is_correct) for a in attempts] == [(1, False), (2, True)]

    async def test_summary_row_keeps_first_answer_wins(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """`progress_service` counts this row for quizzes answered and correct. Redefining it
        would silently move every learner's reported accuracy partway through a study, so the
        history is added ALONGSIDE it rather than replacing it.
        """
        block = await _block(db, enrolled_course["sections"][0].id)
        await client.post(
            QUIZ_URL,
            json={"contentBlockId": str(block.id), "selectedAnswers": ["a"], "isCorrect": False},
            headers=auth_headers,
        )
        await client.post(
            QUIZ_URL,
            json={"contentBlockId": str(block.id), "selectedAnswers": ["b"], "isCorrect": True},
            headers=auth_headers,
        )

        summaries = (
            await db.execute(
                select(QuizBlockResponse).where(
                    QuizBlockResponse.content_block_id == block.id
                )
            )
        ).scalars().all()
        assert len(summaries) == 1
        assert summaries[0].is_correct is False  # unchanged: the first answer

    async def test_repeat_submission_still_returns_200_and_same_row(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """The public contract is unchanged; only what is recorded underneath it changed."""
        block = await _block(db, enrolled_course["sections"][0].id)
        payload = {
            "contentBlockId": str(block.id), "selectedAnswers": ["a"], "isCorrect": True,
        }
        first = await client.post(QUIZ_URL, json=payload, headers=auth_headers)
        second = await client.post(QUIZ_URL, json=payload, headers=auth_headers)

        assert first.status_code == 201
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]

    async def test_attempt_records_timing_and_section(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        section = enrolled_course["sections"][0]
        block = await _block(db, section.id)
        await client.post(
            QUIZ_URL,
            json={
                "contentBlockId": str(block.id),
                "selectedAnswers": ["a"],
                "isCorrect": True,
                "responseTimeMs": 8400,
                "sectionId": str(section.id),
            },
            headers=auth_headers,
        )

        attempt = (await _attempts(db, block.id))[0]
        assert attempt.response_time_ms == 8400
        assert attempt.section_id == section.id

    async def test_attempt_records_the_assistance_that_was_on_screen(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """The join that turns "a hint was shown" into "a hint was shown and the next attempt was
        correct". It records an association, not a cause.
        """
        block = await _block(db, enrolled_course["sections"][0].id)
        await client.post(
            QUIZ_URL,
            json={
                "contentBlockId": str(block.id),
                "selectedAnswers": ["b"],
                "isCorrect": True,
                "assistanceId": "adapt-abc-123",
            },
            headers=auth_headers,
        )

        attempt = (await _attempts(db, block.id))[0]
        assert attempt.assistance_id == "adapt-abc-123"

    async def test_attempts_without_assistance_are_null_not_blank(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """Most answers follow no intervention. Null must mean no help, so that filtering on
        assistance is a real filter rather than one that matches everything.
        """
        block = await _block(db, enrolled_course["sections"][0].id)
        await client.post(
            QUIZ_URL,
            json={"contentBlockId": str(block.id), "selectedAnswers": ["a"], "isCorrect": True},
            headers=auth_headers,
        )

        assert (await _attempts(db, block.id))[0].assistance_id is None

    async def test_attempt_numbers_are_per_block_not_global(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        section = enrolled_course["sections"][0]
        block_a = await _block(db, section.id, sort_order=0)
        block_b = await _block(db, section.id, sort_order=1)

        for block in (block_a, block_b):
            await client.post(
                QUIZ_URL,
                json={"contentBlockId": str(block.id), "selectedAnswers": ["a"],
                      "isCorrect": True},
                headers=auth_headers,
            )

        assert (await _attempts(db, block_a.id))[0].attempt_number == 1
        assert (await _attempts(db, block_b.id))[0].attempt_number == 1


class TestSectionVisits:

    async def test_open_and_close_a_visit(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        section = enrolled_course["sections"][0]
        opened = await client.post(
            VISITS_URL,
            json={"sectionId": str(section.id), "entrySource": "next"},
            headers=auth_headers,
        )
        assert opened.status_code == 201
        visit_id = opened.json()["id"]

        closed = await client.post(
            f"{VISITS_URL}/{visit_id}/close",
            json={"durationSeconds": 92},
            headers=auth_headers,
        )
        assert closed.status_code == 200

        visit = (
            await db.execute(select(SectionVisit).where(SectionVisit.id == uuid.UUID(visit_id)))
        ).scalar_one()
        assert visit.entry_source == "next"
        assert visit.duration_seconds == 92
        assert visit.left_at is not None

    async def test_revisiting_creates_a_second_visit(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """`section_progress` would show one completion for both. Returning to material is one of
        the few struggle signals this paginated interface produces reliably.
        """
        section = enrolled_course["sections"][0]
        for source in ("next", "back"):
            await client.post(
                VISITS_URL,
                json={"sectionId": str(section.id), "entrySource": source},
                headers=auth_headers,
            )

        visits = (
            await db.execute(
                select(SectionVisit).where(SectionVisit.section_id == section.id)
            )
        ).scalars().all()
        assert len(visits) == 2
        assert {v.entry_source for v in visits} == {"next", "back"}

    async def test_closing_twice_is_not_an_error(
        self, client: AsyncClient, enrolled_course, auth_headers
    ):
        """The browser sends this from both a navigation handler and an unload handler."""
        section = enrolled_course["sections"][0]
        opened = await client.post(
            VISITS_URL, json={"sectionId": str(section.id)}, headers=auth_headers
        )
        visit_id = opened.json()["id"]

        first = await client.post(
            f"{VISITS_URL}/{visit_id}/close", json={}, headers=auth_headers
        )
        second = await client.post(
            f"{VISITS_URL}/{visit_id}/close", json={}, headers=auth_headers
        )
        assert first.status_code == 200
        assert second.status_code == 200

    async def test_cannot_close_another_learners_visit(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession
    ):
        """The visit id travels to the browser, so it is client-supplied on the way back."""
        section = enrolled_course["sections"][0]
        stranger = SectionVisit(user_id=uuid.uuid4(), section_id=section.id)
        db.add(stranger)
        await db.commit()
        await db.refresh(stranger)

        resp = await client.post(
            f"{VISITS_URL}/{stranger.id}/close", json={}, headers=auth_headers
        )
        assert resp.status_code == 404

    async def test_designer_cannot_open_a_visit(
        self, client: AsyncClient, enrolled_course, designer_headers
    ):
        resp = await client.post(
            VISITS_URL,
            json={"sectionId": str(enrolled_course["sections"][0].id)},
            headers=designer_headers,
        )
        assert resp.status_code == 403


class TestAssistanceOutcomeThroughTheApi:
    """The ledger's outcome column, resolved by a real quiz submission (migration 023).

    This is the join the whole assistance record exists for, and it crosses two transports: the
    help was delivered over the WebSocket, the answer arrives over REST minutes later.
    """

    async def test_answering_with_an_assistance_id_resolves_the_ledger_row(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession, test_user
    ):
        from app.models.assistance_event import AssistanceEvent
        from app.services import assistance_service

        await assistance_service.record_delivery(
            db,
            adaptation_id="adapt-e2e",
            learner_id=test_user.id,
            session_id="s1",
            cycle_number=2,
            action_type="show_hint",
            delivered=True,
            hint_text="Look at what changes between the two lines.",
        )

        block = await _block(db, enrolled_course["sections"][0].id)
        await client.post(
            QUIZ_URL,
            json={
                "contentBlockId": str(block.id),
                "selectedAnswers": ["b"],
                "isCorrect": True,
                "assistanceId": "adapt-e2e",
            },
            headers=auth_headers,
        )

        row = (
            await db.execute(
                select(AssistanceEvent).where(
                    AssistanceEvent.adaptation_id == "adapt-e2e"
                )
            )
        ).scalar_one()
        assert row.outcome_is_correct is True
        assert row.outcome_attempt_id == (await _attempts(db, block.id))[0].id

    async def test_answering_without_one_leaves_every_ledger_row_untouched(
        self, client: AsyncClient, enrolled_course, auth_headers, db: AsyncSession, test_user
    ):
        """Most answers follow no intervention, and must not be attributed to one."""
        from app.models.assistance_event import AssistanceEvent
        from app.services import assistance_service

        await assistance_service.record_delivery(
            db,
            adaptation_id="adapt-untouched",
            learner_id=test_user.id,
            session_id="s1",
            cycle_number=2,
            action_type="show_hint",
            delivered=True,
        )

        block = await _block(db, enrolled_course["sections"][0].id)
        await client.post(
            QUIZ_URL,
            json={"contentBlockId": str(block.id), "selectedAnswers": ["a"], "isCorrect": True},
            headers=auth_headers,
        )

        row = (
            await db.execute(
                select(AssistanceEvent).where(
                    AssistanceEvent.adaptation_id == "adapt-untouched"
                )
            )
        ).scalar_one()
        assert row.outcome_resolved_at is None
