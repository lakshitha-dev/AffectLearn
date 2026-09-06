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
    # `section_features` accompanies EVERY completion (dark-shipped confusion signals), so a
    # recompletion emits both. The invariant this test protects is that `section_started` fires
    # once and only once — not the total event count.
    assert types == ["section_completed", "section_features"]


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


async def test_quiz_repeat_still_emits_because_it_is_a_real_attempt(
    client: AsyncClient, enrolled_course, auth_headers, section_events, db
):
    """CHANGED with migration 022, deliberately.

    This test previously asserted that a repeat submission emitted NOTHING, because the route
    early-returned on the existing summary row before reaching the emit. That was the bug, not
    the contract: a learner answering a second time IS a second attempt, and suppressing it made
    every attempt after the first invisible to the research record as well as to the database.

    `section_features` counts `quiz_submitted` into `quiz_attempt_count` and `quiz_incorrect_count`
    -- its two strongest struggle signals -- so under the old behaviour both were effectively
    capped at one per block, and a learner who took five tries looked identical to one who took
    one. Emitting per attempt is what makes those features mean what their names say.

    The RESPONSE contract is unchanged and still asserted here: repeats remain 200.
    """
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

    emitted = [e for e in section_events if e["event_type"] == "quiz_submitted"]
    assert len(emitted) == 1
    # And it is identifiable AS a repeat, which is the whole point.
    assert emitted[0]["payload"]["attempt_number"] == 2


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


# ── section_features: client-sent confusion signals (dark-shipped) ────────────


async def test_completion_emits_section_features_with_client_signals(
    client: AsyncClient, enrolled_course, auth_headers, section_events
):
    """Counters sent by the lesson page must survive into the research event verbatim."""
    section = enrolled_course["sections"][0]
    resp = await client.post(
        "/api/v1/section-progress",
        json={
            "sectionId": str(section.id),
            "interactionSignals": {
                "timeOnSectionS": 245.5,
                "viewCount": 3,
                "backNavCount": 2,
                "showAnswerUsed": True,
                "quizAttemptCount": 3,
                "quizIncorrectCount": 2,
                "quizResponseTimeMsMean": 5200.0,
            },
        },
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201)

    feats = [e for e in section_events if e["event_type"] == "section_features"]
    assert len(feats) == 1
    p = feats[0]["payload"]
    assert p["section_id"] == str(section.id)
    assert p["time_on_section_s"] == 245.5
    assert p["back_nav_count"] == 2
    assert p["show_answer_used"] == 1
    assert p["quiz_incorrect_count"] == 2
    # Section shape is resolved server-side from the real content blocks.
    assert p["n_blocks"] >= 0
    assert "schema_version" in p


async def test_completion_without_signals_still_succeeds(
    client: AsyncClient, enrolled_course, auth_headers, section_events
):
    """An older client that does not send signals must still complete sections normally."""
    section = enrolled_course["sections"][0]
    resp = await client.post(
        "/api/v1/section-progress",
        json={"sectionId": str(section.id)},
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201)
    feats = [e for e in section_events if e["event_type"] == "section_features"]
    assert len(feats) == 1
    assert feats[0]["payload"]["time_on_section_s"] == 0.0


async def test_absurd_signal_values_are_rejected_by_validation(
    client: AsyncClient, enrolled_course, auth_headers
):
    """Bounds keep a buggy or hostile client from poisoning the research dataset."""
    section = enrolled_course["sections"][0]
    resp = await client.post(
        "/api/v1/section-progress",
        json={
            "sectionId": str(section.id),
            "interactionSignals": {"backNavCount": -5},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422
