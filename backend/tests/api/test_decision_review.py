"""Expert review of pedagogical decisions.

RQ3 reports Cohen's kappa 0.79 between the fine-tuned agent and the rule policy it was trained
on. That is fidelity, not pedagogy: an agent faithfully reproducing a bad policy scores
identically. These endpoints let qualified educators rate real decisions instead.

Three properties carry the research value, and each has tests here:

* THE SAMPLE IS THE SAME FOR EVERYONE. Agreement is only defined over decisions two reviewers
  both rated; a fresh random draw per reviewer would leave the overlap to chance.
* REVIEWERS DO NOT SEE THE OUTCOME, or each other's ratings. Either would make a rating partly a
  measure of something other than the reviewer's own judgement.
* KAPPA, NOT RAW AGREEMENT. If ninety per cent of decisions are reasonable, two raters who both
  always say "yes" agree ninety per cent of the time while sharing no judgement at all.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.assistance_event import AssistanceEvent
from app.models.decision_review import DecisionReview
from app.models.user import Role, User

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/reviews"
GOOD = {"appropriateness": 4, "timing": 4, "quality": 3, "restraint": 5}


@pytest_asyncio.fixture
async def second_reviewer(db: AsyncSession) -> User:
    user = User(
        email_address="reviewer2@test.com",
        password_hash=hash_password("Password1!"),
        first_name="Second",
        last_name="Reviewer",
        role=Role.course_designer,
        email_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
def second_reviewer_headers(second_reviewer: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(second_reviewer.id))}"}


async def _decision(db: AsyncSession, n: int, **overrides) -> AssistanceEvent:
    defaults = dict(
        adaptation_id=f"adapt-{n}",
        learner_id=uuid.uuid4(),
        session_id="s1",
        cycle_number=n,
        action_type="show_hint",
        hint_text=f"Consider what changes between the two lines ({n}).",
        rationale="Learner has shown sustained confusion on this section.",
        affect_state="confused",
        affect_source="behavioral",
        affect_confidence=0.81,
        generated=True,
        delivered_at=func.now(),
    )
    defaults.update(overrides)
    row = AssistanceEvent(**defaults)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _decisions(db: AsyncSession, count: int) -> list[AssistanceEvent]:
    return [await _decision(db, i) for i in range(count)]


class TestTheSample:

    async def test_serves_a_decision_to_review(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        await _decisions(db, 3)

        resp = await client.get(f"{BASE}/next", headers=designer_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["hintText"]
        assert body["sampleSize"] == 3

    async def test_two_reviewers_are_shown_the_same_decision_first(
        self, client: AsyncClient, designer_headers, second_reviewer_headers, db: AsyncSession
    ):
        """The property agreement depends on. A fresh random draw per reviewer would leave the
        overlap between them to chance."""
        await _decisions(db, 5)

        first = (await client.get(f"{BASE}/next", headers=designer_headers)).json()
        second = (await client.get(f"{BASE}/next", headers=second_reviewer_headers)).json()

        assert first["assistanceEventId"] == second["assistanceEventId"]

    async def test_a_reviewer_is_not_shown_the_same_decision_twice(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        await _decisions(db, 3)
        first = (await client.get(f"{BASE}/next", headers=designer_headers)).json()

        await client.post(
            BASE,
            json={
                "assistanceEventId": first["assistanceEventId"],
                "ratings": GOOD,
                "wouldMakeSameCall": True,
            },
            headers=designer_headers,
        )

        second = (await client.get(f"{BASE}/next", headers=designer_headers)).json()
        assert second["assistanceEventId"] != first["assistanceEventId"]

    async def test_returns_null_when_the_reviewer_is_done(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        decision = await _decision(db, 0)
        await client.post(
            BASE,
            json={
                "assistanceEventId": str(decision.id),
                "ratings": GOOD,
                "wouldMakeSameCall": True,
            },
            headers=designer_headers,
        )

        resp = await client.get(f"{BASE}/next", headers=designer_headers)
        assert resp.json() is None

    async def test_skips_decisions_with_nothing_to_judge(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        """A selective action carries no prose, so a reviewer has nothing to rate. Including it
        would pad the denominator with items nobody could score."""
        await _decision(db, 0, hint_text=None, action_type="skip_ahead")
        await _decision(db, 1)

        body = (await client.get(f"{BASE}/next", headers=designer_headers)).json()
        assert body["actionType"] == "show_hint"
        assert body["sampleSize"] == 1

    async def test_skips_offers_the_learner_never_received(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        await _decision(db, 0, delivered_at=None, delivery_failed=True)
        await _decision(db, 1)

        body = (await client.get(f"{BASE}/next", headers=designer_headers)).json()
        assert body["sampleSize"] == 1


class TestWhatAReviewerSees:

    async def test_shows_the_reasoning_not_only_the_output(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        """A rubric applied to the hint text alone cannot judge whether the DECISION was sound."""
        await _decision(db, 0)

        body = (await client.get(f"{BASE}/next", headers=designer_headers)).json()
        assert "sustained confusion" in body["rationale"]
        assert body["affectState"] == "confused"

    async def test_says_whether_a_model_or_the_fallback_wrote_it(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        """Production serves the rule map. A review pooling the two would report a quality figure
        for "the agent" that is partly the fallback's."""
        await _decision(db, 0, generated=False, fallback=True, fallback_reason="vllm_timeout")

        body = (await client.get(f"{BASE}/next", headers=designer_headers)).json()
        assert body["generated"] is False
        assert body["fallbackReason"] == "vllm_timeout"

    async def test_never_reveals_the_outcome(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        """Knowing the learner answered correctly turns "was this a good decision" into "did it
        happen to work", and a reviewer told the outcome cannot un-know it."""
        await _decision(db, 0, outcome_is_correct=True, outcome_attempt_id=None)

        body = (await client.get(f"{BASE}/next", headers=designer_headers)).json()
        assert "outcomeIsCorrect" not in body
        assert "outcome" not in str(body).lower().replace("outcomeisrecorded", "")

    async def test_never_reveals_the_learner(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        decision = await _decision(db, 0)

        body = (await client.get(f"{BASE}/next", headers=designer_headers)).json()
        assert str(decision.learner_id) not in str(body)


class TestSubmission:

    async def test_records_a_rating(
        self, client: AsyncClient, designer_headers, test_designer, db: AsyncSession
    ):
        decision = await _decision(db, 0)

        resp = await client.post(
            BASE,
            json={
                "assistanceEventId": str(decision.id),
                "ratings": GOOD,
                "wouldMakeSameCall": False,
                "comment": "Too early — they had barely read it.",
            },
            headers=designer_headers,
        )
        assert resp.status_code == 201

        review = (
            await db.execute(
                select(DecisionReview).where(DecisionReview.reviewer_id == test_designer.id)
            )
        ).scalar_one()
        assert review.would_make_same_call is False
        assert review.ratings["timing"] == 4

    async def test_rejects_a_partial_rating(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        """Pooling partial reviews with complete ones makes a per-dimension mean computed over
        silently different denominators."""
        decision = await _decision(db, 0)

        resp = await client.post(
            BASE,
            json={
                "assistanceEventId": str(decision.id),
                "ratings": {"appropriateness": 4},
                "wouldMakeSameCall": True,
            },
            headers=designer_headers,
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"]["code"] == "INVALID_RATING"

    async def test_rejects_an_out_of_range_rating(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        decision = await _decision(db, 0)

        resp = await client.post(
            BASE,
            json={
                "assistanceEventId": str(decision.id),
                "ratings": {**GOOD, "quality": 9},
                "wouldMakeSameCall": True,
            },
            headers=designer_headers,
        )
        assert resp.status_code == 422

    async def test_resubmitting_updates_rather_than_duplicating(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        """A reviewer correcting a slip must not be counted twice in every agreement statistic
        computed afterwards."""
        decision = await _decision(db, 0)
        payload = {
            "assistanceEventId": str(decision.id),
            "ratings": GOOD,
            "wouldMakeSameCall": True,
        }
        await client.post(BASE, json=payload, headers=designer_headers)
        await client.post(
            BASE, json={**payload, "wouldMakeSameCall": False}, headers=designer_headers
        )

        rows = (
            await db.execute(
                select(DecisionReview).where(
                    DecisionReview.assistance_event_id == decision.id
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].would_make_same_call is False


class TestAgreement:

    async def _rate(self, client, decision_id, headers, same_call):
        await client.post(
            BASE,
            json={
                "assistanceEventId": str(decision_id),
                "ratings": GOOD,
                "wouldMakeSameCall": same_call,
            },
            headers=headers,
        )

    async def test_reports_agreement_per_pair_of_reviewers(
        self, client: AsyncClient, designer_headers, second_reviewer_headers, db: AsyncSession
    ):
        decisions = await _decisions(db, 4)
        for i, decision in enumerate(decisions):
            await self._rate(client, decision.id, designer_headers, i % 2 == 0)
            await self._rate(client, decision.id, second_reviewer_headers, i % 2 == 0)

        summary = (await client.get(f"{BASE}/summary", headers=designer_headers)).json()
        assert summary["reviewerCount"] == 2
        pair = summary["pairwiseAgreement"][0]
        assert pair["sharedDecisions"] == 4
        assert pair["rawAgreement"] == 100.0
        assert pair["cohensKappa"] == 1.0

    async def test_agreement_is_computed_only_over_shared_decisions(
        self, client: AsyncClient, designer_headers, second_reviewer_headers, db: AsyncSession
    ):
        decisions = await _decisions(db, 4)
        for decision in decisions:
            await self._rate(client, decision.id, designer_headers, True)
        # The second reviewer rates only two of them.
        for decision in decisions[:2]:
            await self._rate(client, decision.id, second_reviewer_headers, True)

        summary = (await client.get(f"{BASE}/summary", headers=designer_headers)).json()
        assert summary["pairwiseAgreement"][0]["sharedDecisions"] == 2

    async def test_no_pair_is_reported_for_a_single_reviewer(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        decision = await _decision(db, 0)
        await self._rate(client, decision.id, designer_headers, True)

        summary = (await client.get(f"{BASE}/summary", headers=designer_headers)).json()
        assert summary["pairwiseAgreement"] == []

    async def test_summary_reports_per_dimension_means(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        decision = await _decision(db, 0)
        await self._rate(client, decision.id, designer_headers, True)

        summary = (await client.get(f"{BASE}/summary", headers=designer_headers)).json()
        assert summary["dimensionMeans"]["restraint"] == 5.0

    async def test_summary_distinguishes_exhausted_from_empty(
        self, client: AsyncClient, designer_headers, db: AsyncSession
    ):
        """Before a pilot the likely state is "almost nothing to review", which is a different
        problem from "the sample is done"."""
        await _decisions(db, 2)

        summary = (
            await client.get(f"{BASE}/summary?sampleSize=1", headers=designer_headers)
        ).json()
        assert summary["sampleSize"] == 1
        assert summary["reviewableTotal"] == 2


class TestAccess:

    async def test_learners_cannot_review(self, client: AsyncClient, auth_headers):
        assert (await client.get(f"{BASE}/next", headers=auth_headers)).status_code == 403

    async def test_designers_can_review(self, client: AsyncClient, designer_headers):
        """Course designers are the educators on this platform. Requiring an admin account to
        rate a hint would mean handing out admin, or transcribing ratings by hand."""
        assert (await client.get(f"{BASE}/summary", headers=designer_headers)).status_code == 200

    async def test_admins_can_review(self, client: AsyncClient, admin_headers):
        assert (await client.get(f"{BASE}/summary", headers=admin_headers)).status_code == 200

    async def test_the_rubric_is_served_not_hardcoded(
        self, client: AsyncClient, designer_headers
    ):
        body = (await client.get(f"{BASE}/rubric", headers=designer_headers)).json()
        assert set(body["dimensions"]) == set(GOOD)
        assert body["minRating"] == 1 and body["maxRating"] == 5
