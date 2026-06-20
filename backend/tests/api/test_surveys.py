"""Tests for the Story 6.4 post-study satisfaction survey API.

`POST /surveys/satisfaction` persists the authenticated learner's four AC-dimension Likert
answers as one row per user (idempotent upsert) and emits a non-blocking `survey_completed`
research event; `GET /surveys/satisfaction` returns the caller's own submission. Both endpoints
require auth and operate ONLY on the caller's row — a body `user_id` is never trusted.

We patch the research-event emitter so no Redis / live socket is needed (mirror
test_questionnaire.py). The >= 4.0/5 target is a research metric only — low scores still submit.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

import app.api.routes.surveys as surveys_route
from app.core.security import create_access_token, hash_password
from app.models.survey_response import SurveyResponse
from app.models.user import Role, User

POST_URL = "/api/v1/surveys/satisfaction"
GET_URL = "/api/v1/surveys/satisfaction"

pytestmark = pytest.mark.asyncio


def _valid_responses(**overrides):
    base = {
        "Q1": "5",  # perceived adaptation quality (UX anchor)
        "Q2": "4",  # learning experience
        "Q3": "4",  # willingness to continue
        "Q4": "5",  # overall satisfaction
    }
    base.update(overrides)
    return base


@pytest.fixture
def captured_events(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(surveys_route, "emit_research_event", fake_emit)
    return events


class TestSubmit:
    async def test_submit_persists_linked_to_user(
        self, client: AsyncClient, test_user, auth_headers, captured_events, db
    ):
        resp = await client.post(
            POST_URL, json={"responses": _valid_responses()}, headers=auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["userId"] == str(test_user.id)
        assert body["responses"]["Q1"] == "5"
        assert body["submittedAt"] is not None

        result = await db.execute(
            select(SurveyResponse).where(SurveyResponse.user_id == test_user.id)
        )
        row = result.scalar_one()
        assert row.responses["Q4"] == "5"

    async def test_submit_emits_research_event(
        self, client: AsyncClient, test_user, auth_headers, captured_events
    ):
        resp = await client.post(
            POST_URL, json={"responses": _valid_responses()}, headers=auth_headers
        )
        assert resp.status_code == 200
        events = [e for e in captured_events if e["event_type"] == "survey_completed"]
        assert len(events) == 1
        evt = events[0]
        assert evt["learner_id"] == str(test_user.id)
        assert evt["payload"]["user_id"] == str(test_user.id)
        assert evt["payload"]["answered_count"] == 4
        # mean of 5,4,4,5 = 4.5 (research metric only)
        assert evt["payload"]["mean_score"] == 4.5
        # No raw answer values leak into the event payload.
        assert "Q1" not in evt["payload"]
        assert "responses" not in evt["payload"]

    async def test_low_scores_still_submit_and_no_gate(
        self, client: AsyncClient, test_user, auth_headers, captured_events
    ):
        """AC7: a low (< 4.0) average must still persist and reach success — not a gate."""
        resp = await client.post(
            POST_URL,
            json={"responses": _valid_responses(Q1="1", Q2="1", Q3="2", Q4="1")},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        events = [e for e in captured_events if e["event_type"] == "survey_completed"]
        assert events[0]["payload"]["mean_score"] == 1.25

    async def test_resubmit_is_idempotent_upsert(
        self, client: AsyncClient, test_user, auth_headers, captured_events, db
    ):
        r1 = await client.post(
            POST_URL, json={"responses": _valid_responses(Q1="2")}, headers=auth_headers
        )
        assert r1.status_code == 200
        r2 = await client.post(
            POST_URL, json={"responses": _valid_responses(Q1="5")}, headers=auth_headers
        )
        assert r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]
        assert r2.json()["responses"]["Q1"] == "5"

        result = await db.execute(
            select(SurveyResponse).where(SurveyResponse.user_id == test_user.id)
        )
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].responses["Q1"] == "5"

    async def test_body_user_id_is_ignored(
        self, client: AsyncClient, test_user, auth_headers, captured_events, db
    ):
        """A user_id smuggled in the body must NOT change whose row is written."""
        import uuid

        attacker_id = str(uuid.uuid4())
        resp = await client.post(
            POST_URL,
            json={"userId": attacker_id, "responses": _valid_responses()},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["userId"] == str(test_user.id)

        result = await db.execute(select(SurveyResponse))
        rows = result.scalars().all()
        assert len(rows) == 1
        assert str(rows[0].user_id) == str(test_user.id)

    async def test_event_emit_failure_does_not_crash_request(
        self, client: AsyncClient, test_user, auth_headers, monkeypatch, db
    ):
        async def boom(event):
            raise RuntimeError("redis down")

        monkeypatch.setattr(surveys_route, "emit_research_event", boom)
        resp = await client.post(
            POST_URL, json={"responses": _valid_responses()}, headers=auth_headers
        )
        assert resp.status_code == 200
        # The durable record still persisted.
        result = await db.execute(select(SurveyResponse))
        assert len(result.scalars().all()) == 1


class TestValidation:
    async def test_unauthenticated_returns_401_or_403(self, client: AsyncClient):
        resp = await client.post(POST_URL, json={"responses": _valid_responses()})
        assert resp.status_code in (401, 403)

    async def test_missing_required_key_returns_422(
        self, client: AsyncClient, test_user, auth_headers, captured_events
    ):
        bad = _valid_responses()
        del bad["Q1"]
        resp = await client.post(POST_URL, json={"responses": bad}, headers=auth_headers)
        assert resp.status_code == 422

    async def test_unknown_key_returns_422(
        self, client: AsyncClient, test_user, auth_headers, captured_events
    ):
        bad = _valid_responses(Q99="3")
        resp = await client.post(POST_URL, json={"responses": bad}, headers=auth_headers)
        assert resp.status_code == 422

    async def test_out_of_vocab_value_returns_422(
        self, client: AsyncClient, test_user, auth_headers, captured_events
    ):
        bad = _valid_responses(Q1="9")
        resp = await client.post(POST_URL, json={"responses": bad}, headers=auth_headers)
        assert resp.status_code == 422

    async def test_non_string_value_returns_422(
        self, client: AsyncClient, test_user, auth_headers, captured_events
    ):
        bad = _valid_responses(Q1=5)
        resp = await client.post(POST_URL, json={"responses": bad}, headers=auth_headers)
        assert resp.status_code == 422


class TestGet:
    async def test_get_returns_own_submission(
        self, client: AsyncClient, test_user, auth_headers, captured_events
    ):
        await client.post(
            POST_URL, json={"responses": _valid_responses()}, headers=auth_headers
        )
        resp = await client.get(GET_URL, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["userId"] == str(test_user.id)
        assert resp.json()["responses"]["Q2"] == "4"

    async def test_get_404_when_none(self, client: AsyncClient, test_user, auth_headers):
        resp = await client.get(GET_URL, headers=auth_headers)
        assert resp.status_code == 404
        assert resp.json()["detail"]["error"]["code"] == "NOT_FOUND"

    async def test_get_only_returns_callers_row(
        self, client: AsyncClient, test_user, auth_headers, captured_events, db
    ):
        """A second learner's submission is never visible to the first caller."""
        await client.post(
            POST_URL, json={"responses": _valid_responses(Q1="2")}, headers=auth_headers
        )

        other = User(
            email_address="other-survey@test.com",
            password_hash=hash_password("Password1!"),
            first_name="Other",
            last_name="Learner",
            role=Role.learner,
        )
        db.add(other)
        await db.commit()
        await db.refresh(other)
        other_headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}
        await client.post(
            POST_URL, json={"responses": _valid_responses(Q1="5")}, headers=other_headers
        )

        r_first = await client.get(GET_URL, headers=auth_headers)
        r_other = await client.get(GET_URL, headers=other_headers)
        assert r_first.json()["responses"]["Q1"] == "2"
        assert r_other.json()["responses"]["Q1"] == "5"
        assert r_first.json()["userId"] == str(test_user.id)
        assert r_other.json()["userId"] == str(other.id)
