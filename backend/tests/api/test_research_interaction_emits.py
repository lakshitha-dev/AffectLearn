"""Story 6.5 emit-inventory tests for the NEW learner-interaction research events.

Asserts the producer gap is closed: `section_started` / `section_completed` (section-progress
route), `quiz_submitted` (quiz-response route), and `exercise_attempted` (assessment attempt
route) now fire via `_safe_emit` with the FULL envelope — including top-level `phase`/`group` —
and that an emit failure NEVER crashes the learner's request (NFR22). The emitter is
monkeypatched so no Redis / live socket is needed (mirror test_questionnaire.py).
"""

import pytest
from httpx import AsyncClient

import app.api.routes.assessments as assessments_route
import app.api.routes.section_progress as section_progress_route
from tests.api.test_assessments import create_test_assessment
from tests.api.test_quiz_responses import _create_content_block

pytestmark = pytest.mark.asyncio


@pytest.fixture
def section_events(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(section_progress_route, "emit_research_event", fake_emit)
    return events


@pytest.fixture
def assessment_events(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(assessments_route, "emit_research_event", fake_emit)
    return events


def _assert_full_envelope(evt, expected_type, learner_id):
    assert evt["event_type"] == expected_type
    assert evt["learner_id"] == str(learner_id)
    assert "session_id" in evt
    assert "cycle_number" in evt
    assert "timestamp" in evt and isinstance(evt["timestamp"], int)
    assert "phase" in evt        # top-level phase present
    assert "group" in evt        # top-level group present
    assert "payload" in evt


# ── section_started / section_completed ─────────────────────────────────────────

async def test_section_complete_emits_started_and_completed(
    client: AsyncClient, enrolled_course, auth_headers, test_user, section_events
):
    section = enrolled_course["sections"][0]
    resp = await client.post(
        "/api/v1/section-progress",
        json={"sectionId": str(section.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    types = [e["event_type"] for e in section_events]
    assert "section_started" in types  # first completion records start
    assert "section_completed" in types
    completed = next(e for e in section_events if e["event_type"] == "section_completed")
    _assert_full_envelope(completed, "section_completed", test_user.id)
    assert completed["payload"]["section_id"] == str(section.id)
    # phase/group resolved to safe defaults (no assignment) — present, not buried in payload.
    assert completed["phase"] == "phase_a"
    assert completed["group"] == "control"


async def test_idempotent_recompletion_emits_only_completed(
    client: AsyncClient, enrolled_course, auth_headers, section_events
):
    section = enrolled_course["sections"][0]
    payload = {"sectionId": str(section.id)}
    await client.post("/api/v1/section-progress", json=payload, headers=auth_headers)
    section_events.clear()
    resp = await client.post("/api/v1/section-progress", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    types = [e["event_type"] for e in section_events]
    assert "section_started" not in types  # not a first completion
    assert types == ["section_completed"]


async def test_section_emit_failure_does_not_crash_request(
    client: AsyncClient, enrolled_course, auth_headers, monkeypatch
):
    async def boom(event):
        raise RuntimeError("redis down")

    monkeypatch.setattr(section_progress_route, "emit_research_event", boom)
    section = enrolled_course["sections"][0]
    resp = await client.post(
        "/api/v1/section-progress",
        json={"sectionId": str(section.id)},
        headers=auth_headers,
    )
    assert resp.status_code == 201  # durable row still written; emit swallowed


# ── quiz_submitted ──────────────────────────────────────────────────────────────

async def test_quiz_response_emits_quiz_submitted(
    client: AsyncClient, enrolled_course, auth_headers, test_user, section_events, db
):
    section = enrolled_course["sections"][0]
    block = await _create_content_block(db, section.id)
    resp = await client.post(
        "/api/v1/quiz-responses",
        json={
            "contentBlockId": str(block.id),
            "selectedAnswers": ["opt-b"],
            "isCorrect": True,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    quiz = [e for e in section_events if e["event_type"] == "quiz_submitted"]
    assert len(quiz) == 1
    _assert_full_envelope(quiz[0], "quiz_submitted", test_user.id)
    assert quiz[0]["payload"]["content_block_id"] == str(block.id)
    assert quiz[0]["payload"]["is_correct"] is True
    # research-safe: raw selected answers never leak into the event
    assert "selected_answers" not in quiz[0]["payload"]


async def test_quiz_idempotent_repeat_does_not_re_emit(
    client: AsyncClient, enrolled_course, auth_headers, section_events, db
):
    section = enrolled_course["sections"][0]
    block = await _create_content_block(db, section.id)
    payload = {
        "contentBlockId": str(block.id),
        "selectedAnswers": ["opt-b"],
        "isCorrect": True,
    }
    await client.post("/api/v1/quiz-responses", json=payload, headers=auth_headers)
    section_events.clear()
    resp = await client.post("/api/v1/quiz-responses", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    assert [e for e in section_events if e["event_type"] == "quiz_submitted"] == []


# ── exercise_attempted ──────────────────────────────────────────────────────────

async def test_submit_attempt_emits_exercise_attempted(
    client: AsyncClient, enrolled_course, designer_headers, auth_headers, test_user,
    assessment_events, db,
):
    assessment_id, module_id = await create_test_assessment(
        client, enrolled_course, designer_headers, db
    )
    r = await client.get(
        f"/api/v1/assessments?module_id={module_id}&type=pre", headers=auth_headers
    )
    answers = [
        {"questionId": q["id"], "selectedOptionId": q["options"][0]["id"]}
        for q in r.json()["questions"]
    ]
    submit = await client.post(
        f"/api/v1/assessments/{assessment_id}/attempts",
        json={"answers": answers},
        headers=auth_headers,
    )
    assert submit.status_code == 201
    ex = [e for e in assessment_events if e["event_type"] == "exercise_attempted"]
    assert len(ex) == 1
    _assert_full_envelope(ex[0], "exercise_attempted", test_user.id)
    assert ex[0]["payload"]["assessment_id"] == str(assessment_id)
    assert ex[0]["payload"]["max_score"] == 2
    # Options are shuffled by assessment_service; score is 0-2 depending on random order.
    assert 0 <= ex[0]["payload"]["score"] <= ex[0]["payload"]["max_score"]


async def test_assessment_emit_failure_does_not_crash_request(
    client: AsyncClient, enrolled_course, designer_headers, auth_headers, monkeypatch, db
):
    assessment_id, module_id = await create_test_assessment(
        client, enrolled_course, designer_headers, db
    )
    r = await client.get(
        f"/api/v1/assessments?module_id={module_id}&type=pre", headers=auth_headers
    )
    answers = [
        {"questionId": q["id"], "selectedOptionId": q["options"][0]["id"]}
        for q in r.json()["questions"]
    ]

    async def boom(event):
        raise RuntimeError("redis down")

    monkeypatch.setattr(assessments_route, "emit_research_event", boom)
    submit = await client.post(
        f"/api/v1/assessments/{assessment_id}/attempts",
        json={"answers": answers},
        headers=auth_headers,
    )
    assert submit.status_code == 201  # attempt persisted; emit swallowed
