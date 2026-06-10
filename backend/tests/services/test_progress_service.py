"""Tests for learner progress aggregation (Story 4.6 AC2)."""

import uuid

import pytest

from app.services import progress_service
from app.services import section_progress_service as sps


@pytest.mark.asyncio
async def test_aggregates_completion_time_affect_and_quizzes(db, test_user, enrolled_course):
    sections = enrolled_course["sections"]  # 12 sections (2 modules x 2 lessons x 3)
    await sps.mark_section_complete(
        db, user_id=test_user.id, section_id=sections[0].id,
        time_spent_seconds=120, affect_states=["engaged", "confused"],
    )
    await sps.mark_section_complete(db, user_id=test_user.id, section_id=sections[1].id)
    await sps.mark_section_complete(db, user_id=test_user.id, section_id=sections[2].id)

    prog = await progress_service.get_learner_progress(db, test_user.id)

    assert len(prog["courses"]) == 1
    course = prog["courses"][0]
    assert course["total_sections"] == 12
    assert course["completed_sections"] == 3
    assert course["percentage"] == pytest.approx(25.0)

    assert len(prog["sections"]) == 3
    timed = next(s for s in prog["sections"] if s["time_spent_seconds"] == 120)
    assert timed["affect_states"] == ["engaged", "confused"]

    assert prog["quizzes"] == {"answered": 0, "correct": 0}


@pytest.mark.asyncio
async def test_unknown_user_returns_empty(db):
    prog = await progress_service.get_learner_progress(db, uuid.uuid4())
    assert prog["courses"] == []
    assert prog["sections"] == []
    assert prog["quizzes"] == {"answered": 0, "correct": 0}
