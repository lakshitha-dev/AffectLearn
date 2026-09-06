"""Content effectiveness: what learners DID, as opposed to how they felt.

`section_features` has been computed and logged on every section completion since it was
written, and nothing has ever read it — its own docstring says it "ships DARK". Sixteen
behavioural features per learner per section, unused. These endpoints read them back and join
them to the assistance ledger and the attempt history.

The tests that matter most here are the ones about NULL. Zero and unknown are different facts: a
section where no help was offered and a section where help was offered but never followed by an
attempt both have "no outcome rate", and returning 0.0 for both would tell a designer that help
never works there.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistance_event import AssistanceEvent
from app.models.course import BlockType, ContentBlock, Course, Lesson, Module, Section
from app.models.quiz_attempt import QuizAttempt
from app.models.research_event import ResearchEvent

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/analytics"
TS0 = 1_700_000_000_000


@pytest_asyncio.fixture
async def course_tree(db: AsyncSession):
    course = Course(title="Effectiveness Course", is_published=True)
    db.add(course)
    await db.flush()
    module = Module(title="M", sort_order=0, course_id=course.id)
    db.add(module)
    await db.flush()
    lesson = Lesson(title="L", sort_order=0, module_id=module.id)
    db.add(lesson)
    await db.flush()
    sections = []
    for i in range(2):
        section = Section(title=f"Section {i}", sort_order=i, lesson_id=lesson.id)
        db.add(section)
        await db.flush()
        sections.append(section)
    block = ContentBlock(
        section_id=sections[0].id, block_type=BlockType.quiz, sort_order=0,
        variant_key="original", variant_group=uuid.uuid4(),
        content={"question": "What is 2+2?", "options": []},
    )
    db.add(block)
    await db.commit()
    return {
        "course_id": course.id,
        "section_ids": [s.id for s in sections],
        "block_id": block.id,
    }


def _features(section_id, learner: str, **overrides):
    payload = {
        "section_id": str(section_id),
        "schema_version": 1,
        "time_on_section_s": 120.0,
        "time_per_100_words": 30.0,
        "view_count": 1,
        "back_nav_count": 0,
        "show_answer_used": 0,
        "quiz_attempt_count": 1,
        "quiz_incorrect_count": 0,
        "quiz_response_time_ms_mean": 5000.0,
        "exercise_attempt_count": 0,
        "adaptation_delivered_count": 0,
        "adaptation_dismissed_count": 0,
        "n_words": 400,
        "n_blocks": 3,
        "n_code_blocks": 0,
        "has_exercise": 0,
        "has_quiz": 1,
    }
    payload.update(overrides)
    return ResearchEvent(
        event_type="section_features",
        learner_id=learner,
        session_id=None,
        cycle_number=0,
        timestamp=TS0,
        sequence_number=1,
        section_id=str(section_id),
        payload=payload,
    )


class TestSectionEffectiveness:

    async def test_reads_back_the_features_that_were_always_being_logged(
        self, client: AsyncClient, course_tree, designer_headers, db: AsyncSession
    ):
        section_id = course_tree["section_ids"][0]
        db.add_all([
            _features(section_id, "u1", back_nav_count=2),
            _features(section_id, "u2", back_nav_count=4),
        ])
        await db.commit()

        resp = await client.get(
            f"{BASE}/courses/{course_tree['course_id']}/effectiveness", headers=designer_headers
        )
        assert resp.status_code == 200
        row = resp.json()["sections"][0]
        assert row["observedLearners"] == 2
        assert row["backNavCount"] == 3.0

    async def test_revisits_are_reported_as_a_share_of_learners(
        self, client: AsyncClient, course_tree, designer_headers, db: AsyncSession
    ):
        """Returning to material already left is one of the few struggle signals a paginated
        reader produces reliably."""
        section_id = course_tree["section_ids"][0]
        db.add_all([
            _features(section_id, "u1", view_count=3),
            _features(section_id, "u2", view_count=1),
        ])
        await db.commit()

        resp = await client.get(
            f"{BASE}/courses/{course_tree['course_id']}/effectiveness", headers=designer_headers
        )
        assert resp.json()["sections"][0]["revisitRate"] == 50.0

    async def test_wrong_answers_are_a_share_of_attempts_not_of_learners(
        self, client: AsyncClient, course_tree, designer_headers, db: AsyncSession
    ):
        """One learner failing four times out of five is a different fact from four learners
        failing once each, and the attempt-level rate is the one that describes the question."""
        section_id = course_tree["section_ids"][0]
        db.add(_features(section_id, "u1", quiz_attempt_count=5, quiz_incorrect_count=4))
        await db.commit()

        resp = await client.get(
            f"{BASE}/courses/{course_tree['course_id']}/effectiveness", headers=designer_headers
        )
        assert resp.json()["sections"][0]["quizIncorrectRate"] == 80.0

    async def test_a_section_with_no_data_reports_null_not_zero(
        self, client: AsyncClient, course_tree, designer_headers
    ):
        """A section nobody has completed has an UNKNOWN dwell time, not a dwell time of zero."""
        resp = await client.get(
            f"{BASE}/courses/{course_tree['course_id']}/effectiveness", headers=designer_headers
        )
        row = resp.json()["sections"][0]
        assert row["observedLearners"] == 0
        assert row["timeOnSectionS"] is None
        assert row["revisitRate"] is None

    async def test_every_section_appears_even_with_no_data(
        self, client: AsyncClient, course_tree, designer_headers
    ):
        """A designer needs to see the sections nobody has reached, which is itself a finding."""
        resp = await client.get(
            f"{BASE}/courses/{course_tree['course_id']}/effectiveness", headers=designer_headers
        )
        assert len(resp.json()["sections"]) == 2

    async def test_thin_samples_are_flagged(
        self, client: AsyncClient, course_tree, designer_headers, db: AsyncSession
    ):
        """A figure from two learners rendered identically to one from forty is worse than
        showing nothing."""
        section_id = course_tree["section_ids"][0]
        db.add(_features(section_id, "u1"))
        await db.commit()

        resp = await client.get(
            f"{BASE}/courses/{course_tree['course_id']}/effectiveness", headers=designer_headers
        )
        assert resp.json()["sections"][0]["insufficientData"] is True


class TestAssistanceRollup:

    async def _offer(self, db, section_id, learner=None, **kwargs):
        row = AssistanceEvent(
            adaptation_id=str(uuid.uuid4()),
            learner_id=learner or uuid.uuid4(),
            session_id="s1",
            cycle_number=1,
            section_id=section_id,
            action_type="show_hint",
            delivered_at=None,
            **kwargs,
        )
        db.add(row)
        await db.commit()
        return row

    async def test_counts_offers_and_dismissals(
        self, client: AsyncClient, course_tree, designer_headers, db: AsyncSession
    ):
        section_id = course_tree["section_ids"][0]
        await self._offer(db, section_id, interaction="dismissed")
        await self._offer(db, section_id, interaction="accepted")

        resp = await client.get(
            f"{BASE}/courses/{course_tree['course_id']}/effectiveness", headers=designer_headers
        )
        assistance = resp.json()["sections"][0]["assistance"]
        assert assistance["offers"] == 2
        assert assistance["dismissalRate"] == 50.0

    async def test_outcome_rate_is_over_followed_up_offers_only(
        self, client: AsyncClient, course_tree, designer_headers, db: AsyncSession
    ):
        """Help never followed by an attempt is UNKNOWN, not failed. Counting it as a failure
        would make a section where learners wandered off look like one where hints do not work."""
        section_id = course_tree["section_ids"][0]
        await self._offer(db, section_id, outcome_is_correct=True)
        await self._offer(db, section_id)  # no outcome recorded

        assistance = (
            await client.get(
                f"{BASE}/courses/{course_tree['course_id']}/effectiveness",
                headers=designer_headers,
            )
        ).json()["sections"][0]["assistance"]

        assert assistance["offers"] == 2
        assert assistance["outcomesRecorded"] == 1
        assert assistance["followedByCorrectRate"] == 100.0

    async def test_no_offers_reports_null_outcome_rate(
        self, client: AsyncClient, course_tree, designer_headers
    ):
        assistance = (
            await client.get(
                f"{BASE}/courses/{course_tree['course_id']}/effectiveness",
                headers=designer_headers,
            )
        ).json()["sections"][0]["assistance"]
        assert assistance["offers"] == 0
        assert assistance["followedByCorrectRate"] is None

    async def test_reports_how_much_help_the_model_actually_wrote(
        self, client: AsyncClient, course_tree, designer_headers, db: AsyncSession
    ):
        """Production has no GPU quota, so the strategist serves its rule map. A dashboard that
        hid this would report the fine-tuned agent's behaviour while showing the fallback's."""
        section_id = course_tree["section_ids"][0]
        await self._offer(db, section_id, generated=True)
        await self._offer(db, section_id, generated=False)

        assistance = (
            await client.get(
                f"{BASE}/courses/{course_tree['course_id']}/effectiveness",
                headers=designer_headers,
            )
        ).json()["sections"][0]["assistance"]
        assert assistance["generatedRate"] == 50.0


class TestQuestionDifficulty:

    async def _attempt(self, db, block_id, section_id, user_id, n, correct, **kwargs):
        db.add(QuizAttempt(
            user_id=user_id, content_block_id=block_id, section_id=section_id,
            attempt_number=n, selected_answers=["a"], is_correct=correct, **kwargs,
        ))
        await db.commit()

    async def test_facility_is_over_all_attempts(
        self, client: AsyncClient, course_tree, designer_headers, db: AsyncSession
    ):
        block_id, section_id = course_tree["block_id"], course_tree["section_ids"][0]
        learner = uuid.uuid4()
        await self._attempt(db, block_id, section_id, learner, 1, False)
        await self._attempt(db, block_id, section_id, learner, 2, True)

        resp = await client.get(f"{BASE}/sections/{section_id}/questions", headers=designer_headers)
        question = resp.json()["questions"][0]
        assert question["attempts"] == 2
        assert question["facility"] == 50.0

    async def test_first_attempt_facility_ignores_later_tries(
        self, client: AsyncClient, course_tree, designer_headers, db: AsyncSession
    ):
        """Later attempts are contaminated by the feedback the earlier ones gave, so first-attempt
        facility is the fairer measure of whether the material taught it."""
        block_id, section_id = course_tree["block_id"], course_tree["section_ids"][0]
        learner = uuid.uuid4()
        await self._attempt(db, block_id, section_id, learner, 1, False)
        await self._attempt(db, block_id, section_id, learner, 2, True)

        question = (
            await client.get(f"{BASE}/sections/{section_id}/questions", headers=designer_headers)
        ).json()["questions"][0]
        assert question["firstAttemptFacility"] == 0.0

    async def test_carries_the_question_text_for_identification(
        self, client: AsyncClient, course_tree, designer_headers
    ):
        section_id = course_tree["section_ids"][0]
        question = (
            await client.get(f"{BASE}/sections/{section_id}/questions", headers=designer_headers)
        ).json()["questions"][0]
        assert question["question"] == "What is 2+2?"

    async def test_an_unattempted_question_reports_null_facility(
        self, client: AsyncClient, course_tree, designer_headers
    ):
        """Nobody has answered it, so its difficulty is unknown — not 0% correct."""
        section_id = course_tree["section_ids"][0]
        question = (
            await client.get(f"{BASE}/sections/{section_id}/questions", headers=designer_headers)
        ).json()["questions"][0]
        assert question["attempts"] == 0
        assert question["facility"] is None


class TestStruggleLeaderboard:

    async def test_ranks_the_hardest_sections_first(
        self, client: AsyncClient, course_tree, designer_headers, db: AsyncSession
    ):
        easy, hard = course_tree["section_ids"]
        for i in range(6):
            db.add(_features(easy, f"e{i}"))
            db.add(_features(hard, f"h{i}", view_count=3, show_answer_used=1,
                             quiz_attempt_count=4, quiz_incorrect_count=3))
        await db.commit()

        resp = await client.get(
            f"{BASE}/courses/{course_tree['course_id']}/struggle", headers=designer_headers
        )
        sections = resp.json()["sections"]
        assert sections[0]["sectionId"] == str(hard)

    async def test_thin_sections_are_excluded_not_ranked(
        self, client: AsyncClient, course_tree, designer_headers, db: AsyncSession
    ):
        """A section completed twice can top any leaderboard by accident, and a designer acting
        on that would rewrite the wrong material."""
        section_id = course_tree["section_ids"][0]
        db.add(_features(section_id, "u1", view_count=9, show_answer_used=1,
                         quiz_attempt_count=9, quiz_incorrect_count=9))
        await db.commit()

        resp = await client.get(
            f"{BASE}/courses/{course_tree['course_id']}/struggle", headers=designer_headers
        )
        assert resp.json()["sections"] == []


class TestAccess:

    async def test_learners_are_refused(
        self, client: AsyncClient, course_tree, auth_headers
    ):
        resp = await client.get(
            f"{BASE}/courses/{course_tree['course_id']}/effectiveness", headers=auth_headers
        )
        assert resp.status_code == 403

    async def test_unknown_course_is_404(self, client: AsyncClient, designer_headers):
        resp = await client.get(
            f"{BASE}/courses/{uuid.uuid4()}/effectiveness", headers=designer_headers
        )
        assert resp.status_code == 404
