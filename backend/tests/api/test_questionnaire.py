"""Tests for the Story 6.3 pre-study questionnaire API.

`POST /onboarding/questionnaire` persists the authenticated learner's Q1–Q14 answers as one
row per user (idempotent upsert) and emits a non-blocking `questionnaire_submitted` research
event; `GET /onboarding/questionnaire` returns the caller's own submission. Both endpoints
require auth and operate ONLY on the caller's row — a body `user_id` is never trusted.

We patch the research-event emitter so no Redis / live socket is needed (mirror
test_ws_self_report.py).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

import app.api.routes.questionnaire as questionnaire_route
from app.core.security import create_access_token, hash_password
from app.models.questionnaire_response import QuestionnaireResponse
from app.models.user import Role, User

POST_URL = "/api/v1/onboarding/questionnaire"
GET_URL = "/api/v1/onboarding/questionnaire"

pytestmark = pytest.mark.asyncio


def _valid_responses(**overrides):
    base = {
        "Q1": "21-23",
        "Q2": "female",
        "Q3": "several_per_week",
        "Q4": "3-5",
        "Q5": "1-2",
        "Q6": "4",
        "Q7": "video",
        "Q8": {"boredom": "2", "confusion": "3", "frustration": "2", "engagement": "4"},
        "Q9": ["take_break", "search_alternatives"],
        "Q10": "yes_once_twice",
        "Q11": "5",
        "Q12": "4",
        "Q13": "4",
        "Q14": "3",
    }
    base.update(overrides)
    return base


@pytest.fixture
def captured_events(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event):
        events.append(event)

    monkeypatch.setattr(questionnaire_route, "emit_research_event", fake_emit)
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
        assert body["responses"]["Q1"] == "21-23"
        assert body["submittedAt"] is not None

        result = await db.execute(
            select(QuestionnaireResponse).where(
                QuestionnaireResponse.user_id == test_user.id
            )
        )
        row = result.scalar_one()
        assert row.responses["Q8"]["engagement"] == "4"

    async def test_submit_emits_research_event(
        self, client: AsyncClient, test_user, auth_headers, captured_events
    ):
        resp = await client.post(
            POST_URL, json={"responses": _valid_responses()}, headers=auth_headers
        )
        assert resp.status_code == 200
        events = [e for e in captured_events if e["event_type"] == "questionnaire_submitted"]
        assert len(events) == 1
        evt = events[0]
        assert evt["learner_id"] == str(test_user.id)
        assert evt["payload"]["user_id"] == str(test_user.id)
        assert evt["payload"]["answered_count"] == 14
        assert evt["payload"]["q9_selected_count"] == 2
        # No raw demographic PII leaks into the event payload.
        assert "Q1" not in evt["payload"]
        assert "responses" not in evt["payload"]

    async def test_resubmit_is_idempotent_upsert(
        self, client: AsyncClient, test_user, auth_headers, captured_events, db
    ):
        r1 = await client.post(
            POST_URL, json={"responses": _valid_responses(Q1="18-20")}, headers=auth_headers
        )
        assert r1.status_code == 200
        r2 = await client.post(
            POST_URL, json={"responses": _valid_responses(Q1="27+")}, headers=auth_headers
        )
        assert r2.status_code == 200
        # Same row id (updated, not inserted twice).
        assert r1.json()["id"] == r2.json()["id"]
        assert r2.json()["responses"]["Q1"] == "27+"

        result = await db.execute(
            select(QuestionnaireResponse).where(
                QuestionnaireResponse.user_id == test_user.id
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].responses["Q1"] == "27+"

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

        result = await db.execute(select(QuestionnaireResponse))
        rows = result.scalars().all()
        assert len(rows) == 1
        assert str(rows[0].user_id) == str(test_user.id)

    async def test_event_emit_failure_does_not_crash_request(
        self, client: AsyncClient, test_user, auth_headers, monkeypatch, db
    ):
        async def boom(event):
            raise RuntimeError("redis down")

        monkeypatch.setattr(questionnaire_route, "emit_research_event", boom)
        resp = await client.post(
            POST_URL, json={"responses": _valid_responses()}, headers=auth_headers
        )
        assert resp.status_code == 200
        # The durable record still persisted.
        result = await db.execute(select(QuestionnaireResponse))
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
        bad = _valid_responses(Q99="anything")
        resp = await client.post(POST_URL, json={"responses": bad}, headers=auth_headers)
        assert resp.status_code == 422

    async def test_out_of_vocab_value_returns_422(
        self, client: AsyncClient, test_user, auth_headers, captured_events
    ):
        bad = _valid_responses(Q1="99-100")
        resp = await client.post(POST_URL, json={"responses": bad}, headers=auth_headers)
        assert resp.status_code == 422

    async def test_malformed_matrix_returns_422(
        self, client: AsyncClient, test_user, auth_headers, captured_events
    ):
        bad = _valid_responses(Q8={"boredom": "2"})  # missing rows
        resp = await client.post(POST_URL, json={"responses": bad}, headers=auth_headers)
        assert resp.status_code == 422

    async def test_invalid_likert_in_matrix_returns_422(
        self, client: AsyncClient, test_user, auth_headers, captured_events
    ):
        bad = _valid_responses(
            Q8={"boredom": "9", "confusion": "3", "frustration": "2", "engagement": "4"}
        )
        resp = await client.post(POST_URL, json={"responses": bad}, headers=auth_headers)
        assert resp.status_code == 422

    async def test_q9_may_be_empty_list(
        self, client: AsyncClient, test_user, auth_headers, captured_events
    ):
        resp = await client.post(
            POST_URL, json={"responses": _valid_responses(Q9=[])}, headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["responses"]["Q9"] == []

    async def test_q9_invalid_option_returns_422(
        self, client: AsyncClient, test_user, auth_headers, captured_events
    ):
        bad = _valid_responses(Q9=["take_break", "teleport"])
        resp = await client.post(POST_URL, json={"responses": bad}, headers=auth_headers)
        assert resp.status_code == 422

    async def test_q9_not_a_list_returns_422(
        self, client: AsyncClient, test_user, auth_headers, captured_events
    ):
        bad = _valid_responses(Q9="take_break")
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
        assert resp.json()["responses"]["Q7"] == "video"

    async def test_get_404_when_none(
        self, client: AsyncClient, test_user, auth_headers
    ):
        resp = await client.get(GET_URL, headers=auth_headers)
        assert resp.status_code == 404
        assert resp.json()["detail"]["error"]["code"] == "NOT_FOUND"

    async def test_get_only_returns_callers_row(
        self, client: AsyncClient, test_user, auth_headers, captured_events, db
    ):
        """A second learner's submission is never visible to the first caller."""
        # First user submits.
        await client.post(
            POST_URL, json={"responses": _valid_responses(Q1="18-20")}, headers=auth_headers
        )

        # Create a second learner and submit a distinct response.
        other = User(
            email_address="other@test.com",
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
            POST_URL, json={"responses": _valid_responses(Q1="27+")}, headers=other_headers
        )

        # Each caller sees only their own row.
        r_first = await client.get(GET_URL, headers=auth_headers)
        r_other = await client.get(GET_URL, headers=other_headers)
        assert r_first.json()["responses"]["Q1"] == "18-20"
        assert r_other.json()["responses"]["Q1"] == "27+"
        assert r_first.json()["userId"] == str(test_user.id)
        assert r_other.json()["userId"] == str(other.id)
