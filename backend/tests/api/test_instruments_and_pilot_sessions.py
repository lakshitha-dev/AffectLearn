"""Pilot questionnaires (lesson feedback, SUS, UEQ-S) and facilitator sitting records (migration 034)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.instrument_response import InstrumentResponse
from app.services.instruments import INSTRUMENTS, sus_score, ueq_s_scales

LESSON = {"difficulty": "4", "easy_to_understand": "3", "noticed_change": "yes",
          "change_helpful": "4", "change_distracting": "2", "responded_to_needs": "3"}
SUS_ALL_3 = {f"q{i}": "3" for i in range(1, 11)}


class TestScoring:
    def test_sus_best_and_worst(self):
        best = {f"q{i}": ("5" if i % 2 else "1") for i in range(1, 11)}
        worst = {f"q{i}": ("1" if i % 2 else "5") for i in range(1, 11)}
        assert sus_score(best) == 100.0
        assert sus_score(worst) == 0.0
        assert sus_score(SUS_ALL_3) == 50.0

    def test_ueq_s_scales_are_centred(self):
        neutral = {f"q{i}": "4" for i in range(1, 9)}
        assert ueq_s_scales(neutral) == {"pragmatic": 0.0, "hedonic": 0.0, "overall": 0.0}
        mixed = {**{f"q{i}": "7" for i in range(1, 5)}, **{f"q{i}": "1" for i in range(5, 9)}}
        assert ueq_s_scales(mixed) == {"pragmatic": 3.0, "hedonic": -3.0, "overall": 0.0}

    def test_validation_refuses_unknown_missing_and_out_of_range(self):
        lf = INSTRUMENTS["lesson_feedback"]
        with pytest.raises(ValueError, match="unknown"):
            lf.validate({**LESSON, "free_text": "x"})
        with pytest.raises(ValueError, match="missing"):
            lf.validate({k: v for k, v in LESSON.items() if k != "difficulty"})
        with pytest.raises(ValueError, match="invalid"):
            lf.validate({**LESSON, "difficulty": "6"})
        # The follow-ups are optional: a learner who noticed nothing is not asked them.
        cleaned = lf.validate({k: v for k, v in LESSON.items()
                               if k not in ("change_helpful", "change_distracting")})
        assert "change_helpful" not in cleaned


class TestSubmit:
    async def test_lesson_feedback_is_stored_with_its_context(
        self, client: AsyncClient, consented_user, auth_headers, db
    ):
        resp = await client.post("/api/v1/instruments/lesson_feedback", headers=auth_headers, json={
            "instrumentVersion": "1.0", "context": {"lessonId": "les-1", "note": "dropped"},
            "responses": LESSON,
        })
        assert resp.status_code == 201, resp.text
        row = (await db.execute(select(InstrumentResponse))).scalar_one()
        assert row.instrument == "lesson_feedback" and row.instrument_version == "1.0"
        assert row.context == {"lessonId": "les-1"}          # identifiers only
        assert row.responses == LESSON and row.skipped is False

    async def test_a_skip_is_recorded_without_answers(
        self, client: AsyncClient, consented_user, auth_headers, db
    ):
        resp = await client.post("/api/v1/instruments/lesson_feedback", headers=auth_headers,
                                 json={"skipped": True, "context": {"lessonId": "les-2"}})
        assert resp.status_code == 201
        row = (await db.execute(select(InstrumentResponse))).scalar_one()
        assert row.skipped is True and row.responses == {}

    async def test_invalid_answers_are_refused(self, client: AsyncClient, consented_user, auth_headers):
        resp = await client.post("/api/v1/instruments/sus", headers=auth_headers,
                                 json={"responses": {**SUS_ALL_3, "q1": "9"}})
        assert resp.status_code == 422

    async def test_unknown_instrument_and_wrong_version(
        self, client: AsyncClient, consented_user, auth_headers
    ):
        assert (await client.post("/api/v1/instruments/nasa_tlx", headers=auth_headers,
                                  json={"responses": {}})).status_code == 404
        assert (await client.post("/api/v1/instruments/sus", headers=auth_headers, json={
            "instrumentVersion": "2.0", "responses": SUS_ALL_3})).status_code == 422

    async def test_a_learner_who_has_not_consented_is_refused(
        self, client: AsyncClient, test_user, auth_headers
    ):
        resp = await client.post("/api/v1/instruments/sus", headers=auth_headers,
                                 json={"responses": SUS_ALL_3})
        assert resp.status_code == 403

    async def test_designers_cannot_submit(self, client: AsyncClient, designer_headers):
        resp = await client.post("/api/v1/instruments/sus", headers=designer_headers,
                                 json={"responses": SUS_ALL_3})
        assert resp.status_code == 403

    async def test_mine_lists_what_was_answered(
        self, client: AsyncClient, consented_user, auth_headers
    ):
        await client.post("/api/v1/instruments/lesson_feedback", headers=auth_headers,
                          json={"context": {"lessonId": "les-1"}, "responses": LESSON})
        await client.post("/api/v1/instruments/sus", headers=auth_headers,
                          json={"responses": SUS_ALL_3})
        mine = (await client.get("/api/v1/instruments/mine?instrument=lesson_feedback",
                                 headers=auth_headers)).json()
        assert [m["context"] for m in mine] == [{"lessonId": "les-1"}]

    async def test_the_research_event_carries_the_score(
        self, client: AsyncClient, consented_user, auth_headers, monkeypatch
    ):
        import app.api.routes.instruments as routes

        events: list[dict] = []

        async def capture(event):
            events.append(event)

        monkeypatch.setattr(routes, "emit_research_event", capture)
        await client.post("/api/v1/instruments/sus", headers=auth_headers,
                          json={"responses": SUS_ALL_3})
        (event,) = events
        assert event["event_type"] == "instrument_submitted"
        assert event["payload"]["sus_score"] == 50.0


class TestPilotSessions:
    async def test_start_reads_arm_and_versions_then_end_records_the_reason(
        self, client: AsyncClient, consented_user, admin_headers
    ):
        start = await client.post("/api/v1/admin/pilot/sessions", headers=admin_headers, json={
            "userId": str(consented_user.id), "participantCode": "P007",
            "protocolVersion": "pilot-1.0", "device": {"browser": "Chrome 140", "camera": "built-in"},
        })
        assert start.status_code == 201, start.text
        body = start.json()
        assert body["participantCode"] == "P007"
        assert body["group"] == "control"            # unassigned learners default to control
        assert body["consentVersion"] == consented_user.consent_version
        assert body["endedAt"] is None

        end = await client.post(f"/api/v1/admin/pilot/sessions/{body['id']}/end",
                                headers=admin_headers,
                                json={"endReason": "completed", "deviationNotes": "none"})
        assert end.status_code == 200
        assert end.json()["endReason"] == "completed" and end.json()["endedAt"]

        again = await client.post(f"/api/v1/admin/pilot/sessions/{body['id']}/end",
                                  headers=admin_headers, json={"endReason": "completed"})
        assert again.status_code == 409

    async def test_end_reason_must_be_known(self, client: AsyncClient, consented_user, admin_headers):
        sid = (await client.post("/api/v1/admin/pilot/sessions", headers=admin_headers, json={
            "userId": str(consented_user.id), "participantCode": "P008"})).json()["id"]
        resp = await client.post(f"/api/v1/admin/pilot/sessions/{sid}/end", headers=admin_headers,
                                 json={"endReason": "bored"})
        assert resp.status_code == 422

    async def test_codes_carry_no_free_text(self, client: AsyncClient, consented_user, admin_headers):
        resp = await client.post("/api/v1/admin/pilot/sessions", headers=admin_headers, json={
            "userId": str(consented_user.id), "participantCode": "Jane Doe"})
        assert resp.status_code == 422

    async def test_learners_cannot_use_it(self, client: AsyncClient, consented_user, auth_headers):
        resp = await client.post("/api/v1/admin/pilot/sessions", headers=auth_headers, json={
            "userId": str(uuid.uuid4()), "participantCode": "P009"})
        assert resp.status_code == 403
