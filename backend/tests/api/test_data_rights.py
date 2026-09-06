"""Erasure, export and password change — the code behind the participant-facing promises.

The consent form and the privacy policy both commit to deleting a participant's data on request.
Until these endpoints existed the commitment was honoured by hand, which is not a control.

The most important test in this file is `test_erasure_reaches_research_events`. `research_events`
has no foreign key to `users` — deliberately, so the research record survives the content and
accounts it refers to — which means the database cascade does NOT remove it. An erasure that
relied on the cascade would report success while leaving every affect reading, self-report and
adaptation for that participant in place: the worst possible outcome, because it looks like
compliance.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models.enrollment import Enrollment
from app.models.research_event import ResearchEvent
from app.models.section_progress import SectionProgress
from app.models.user import User

pytestmark = pytest.mark.asyncio

EXPORT_URL = "/api/v1/auth/me/export"
DELETE_URL = "/api/v1/auth/me/delete"
CHANGE_PASSWORD_URL = "/api/v1/auth/change-password"


async def _seed_research_events(db: AsyncSession, learner_id, n: int = 3) -> None:
    db.add_all([
        ResearchEvent(
            event_type="facial_affect_detected",
            learner_id=str(learner_id),
            session_id="s1",
            cycle_number=i,
            timestamp=1_700_000_000_000 + i,
            sequence_number=i,
            payload={"affect_state": "confused"},
        )
        for i in range(1, n + 1)
    ])
    await db.commit()


class TestErasure:

    async def test_erasure_reaches_research_events(
        self, client: AsyncClient, auth_headers, test_user, db: AsyncSession
    ):
        """The rows no cascade would remove. See the module docstring."""
        await _seed_research_events(db, test_user.id)

        resp = await client.post(
            DELETE_URL,
            json={"password": "Password1!", "confirm": "DELETE"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        remaining = (
            await db.execute(
                select(func.count(ResearchEvent.id)).where(
                    ResearchEvent.learner_id == str(test_user.id)
                )
            )
        ).scalar_one()
        assert remaining == 0

    async def test_erasure_removes_the_account(
        self, client: AsyncClient, auth_headers, test_user, db: AsyncSession
    ):
        user_id = test_user.id
        await client.post(
            DELETE_URL,
            json={"password": "Password1!", "confirm": "DELETE"},
            headers=auth_headers,
        )

        assert (
            await db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none() is None

    async def test_erasure_cascades_to_learning_records(
        self, client: AsyncClient, auth_headers, test_user, enrolled_course, db: AsyncSession
    ):
        user_id = test_user.id
        await client.post(
            DELETE_URL,
            json={"password": "Password1!", "confirm": "DELETE"},
            headers=auth_headers,
        )

        for model, column in (
            (Enrollment, Enrollment.user_id),
            (SectionProgress, SectionProgress.user_id),
        ):
            count = (
                await db.execute(select(func.count(model.id)).where(column == user_id))
            ).scalar_one()
            assert count == 0, f"{model.__tablename__} survived erasure"

    async def test_receipt_reports_what_was_removed(
        self, client: AsyncClient, auth_headers, test_user, db: AsyncSession
    ):
        """"Deleted" with no numbers is indistinguishable from a no-op that returned 200."""
        await _seed_research_events(db, test_user.id, n=4)

        resp = await client.post(
            DELETE_URL,
            json={"password": "Password1!", "confirm": "DELETE"},
            headers=auth_headers,
        )
        assert resp.json()["deleted"]["researchEvents"] == 4

    async def test_a_wrong_password_erases_nothing(
        self, client: AsyncClient, auth_headers, test_user, db: AsyncSession
    ):
        resp = await client.post(
            DELETE_URL,
            json={"password": "NotMyPassword1!", "confirm": "DELETE"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert await db.get(User, test_user.id) is not None

    async def test_confirmation_is_required(
        self, client: AsyncClient, auth_headers, test_user, db: AsyncSession
    ):
        """A bare boolean is too easy to send by accident from a half-written client, and this
        endpoint destroys a participant's entire record."""
        resp = await client.post(
            DELETE_URL,
            json={"password": "Password1!", "confirm": "yes"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"]["code"] == "CONFIRMATION_REQUIRED"
        assert await db.get(User, test_user.id) is not None

    async def test_unauthenticated_cannot_erase(self, client: AsyncClient):
        resp = await client.post(
            DELETE_URL, json={"password": "Password1!", "confirm": "DELETE"}
        )
        assert resp.status_code in (401, 403)

    async def test_erasure_leaves_other_learners_alone(
        self, client: AsyncClient, auth_headers, test_user, db: AsyncSession
    ):
        stranger_id = uuid.uuid4()
        await _seed_research_events(db, stranger_id, n=2)
        await _seed_research_events(db, test_user.id, n=2)

        await client.post(
            DELETE_URL,
            json={"password": "Password1!", "confirm": "DELETE"},
            headers=auth_headers,
        )

        survived = (
            await db.execute(
                select(func.count(ResearchEvent.id)).where(
                    ResearchEvent.learner_id == str(stranger_id)
                )
            )
        ).scalar_one()
        assert survived == 2


class TestExport:

    async def test_export_includes_the_account(
        self, client: AsyncClient, auth_headers, test_user
    ):
        resp = await client.get(EXPORT_URL, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["account"]["emailAddress"] == test_user.email_address

    async def test_export_includes_the_research_record(
        self, client: AsyncClient, auth_headers, test_user, db: AsyncSession
    ):
        """A subject-access response that omitted the telemetry would answer an easier question
        than the one being asked."""
        await _seed_research_events(db, test_user.id, n=3)

        resp = await client.get(EXPORT_URL, headers=auth_headers)
        assert len(resp.json()["researchEvents"]) == 3

    async def test_export_covers_every_learner_table(
        self, client: AsyncClient, auth_headers
    ):
        body = (await client.get(EXPORT_URL, headers=auth_headers)).json()
        for key in (
            "enrollments", "sectionProgress", "sectionVisits", "quizAttempts",
            "assessmentAttempts", "assistanceEvents", "questionnaireResponses",
            "surveyResponses", "researchEvents",
        ):
            assert key in body, f"export omits {key}"

    async def test_export_is_scoped_to_the_caller(
        self, client: AsyncClient, auth_headers, test_user, db: AsyncSession
    ):
        await _seed_research_events(db, uuid.uuid4(), n=5)
        await _seed_research_events(db, test_user.id, n=1)

        body = (await client.get(EXPORT_URL, headers=auth_headers)).json()
        assert len(body["researchEvents"]) == 1

    async def test_unauthenticated_cannot_export(self, client: AsyncClient):
        resp = await client.get(EXPORT_URL)
        assert resp.status_code in (401, 403)


class TestChangePassword:

    async def test_changes_the_password(
        self, client: AsyncClient, auth_headers, test_user, db: AsyncSession
    ):
        resp = await client.post(
            CHANGE_PASSWORD_URL,
            json={"currentPassword": "Password1!", "newPassword": "BrandNew1!"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        await db.refresh(test_user)
        assert verify_password("BrandNew1!", test_user.password_hash)

    async def test_requires_the_current_password(
        self, client: AsyncClient, auth_headers, test_user, db: AsyncSession
    ):
        """A token left behind on a shared machine should not be enough to lock the real owner
        out of their own account."""
        resp = await client.post(
            CHANGE_PASSWORD_URL,
            json={"currentPassword": "WrongOne1!", "newPassword": "BrandNew1!"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

        await db.refresh(test_user)
        assert verify_password("Password1!", test_user.password_hash)

    async def test_rejects_a_weak_new_password(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            CHANGE_PASSWORD_URL,
            json={"currentPassword": "Password1!", "newPassword": "short"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_unauthenticated_cannot_change_a_password(self, client: AsyncClient):
        resp = await client.post(
            CHANGE_PASSWORD_URL,
            json={"currentPassword": "Password1!", "newPassword": "BrandNew1!"},
        )
        assert resp.status_code in (401, 403)
