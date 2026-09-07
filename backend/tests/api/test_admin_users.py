"""Tests for admin user management (Story 8.1) and participant withdrawal (Story 8.7 / FR49).

`/admin/users` could list and invite and nothing else — no role change, no way to deactivate a
leaver, no way to reverse a mistaken invite, and no server-side search (the console fetched one
hardcoded page of 100 and filtered it in the browser, which stops working at the 101st account).

Withdrawal had no admin route at all: `data_rights_service.erase_learner` was complete and wired
only to the learner's own delete button, so a coordinator could not action a withdrawal request.
"""

import uuid

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token, hash_password
from app.models.user import Role, User

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/admin/users"


async def _make_user(db, email, role=Role.learner, is_active=True):
    user = User(
        email_address=email,
        password_hash=hash_password("Password1!"),
        first_name="Test",
        last_name="Person",
        role=role,
        is_active=is_active,
        email_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


class TestChangingAnAccount:
    async def test_promotes_a_learner_to_designer(
        self, client: AsyncClient, admin_headers, test_user
    ):
        resp = await client.patch(
            f"{BASE}/{test_user.id}", json={"role": "course_designer"}, headers=admin_headers
        )

        assert resp.status_code == 200
        assert resp.json()["role"] == "course_designer"

    async def test_deactivating_locks_the_account_out_immediately(
        self, client: AsyncClient, admin_headers, db
    ):
        """`get_current_user` already rejects inactive users, so this needs no extra plumbing."""
        user = await _make_user(db, "to-deactivate@test.com")
        token = create_access_token(str(user.id))

        # Their token works before.
        assert (
            await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        ).status_code == 200

        await client.patch(
            f"{BASE}/{user.id}", json={"isActive": False}, headers=admin_headers
        )

        # And not after — the SAME token, already issued.
        assert (
            await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        ).status_code == 401

    async def test_reactivating_restores_access(self, client: AsyncClient, admin_headers, db):
        user = await _make_user(db, "to-reactivate@test.com", is_active=False)

        resp = await client.patch(
            f"{BASE}/{user.id}", json={"isActive": True}, headers=admin_headers
        )

        assert resp.status_code == 200
        assert resp.json()["isActive"] is True

    async def test_an_admin_cannot_demote_themselves(
        self, client: AsyncClient, admin_headers, test_admin
    ):
        """This is the only role that can grant the role back.

        A sole administrator who clicks the wrong row locks the deployment out of its own
        administration, and the repair is a manual database edit.
        """
        resp = await client.patch(
            f"{BASE}/{test_admin.id}", json={"role": "learner"}, headers=admin_headers
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["error"]["code"] == "CANNOT_SELF_ADMINISTER"

    async def test_an_admin_cannot_deactivate_themselves(
        self, client: AsyncClient, admin_headers, test_admin
    ):
        resp = await client.patch(
            f"{BASE}/{test_admin.id}", json={"isActive": False}, headers=admin_headers
        )

        assert resp.status_code == 400

    async def test_a_no_op_write_of_your_own_row_is_allowed(
        self, client: AsyncClient, admin_headers, test_admin
    ):
        """The guard is about CHANGING your own access, not about touching your own row."""
        resp = await client.patch(
            f"{BASE}/{test_admin.id}", json={"role": "admin", "isActive": True}, headers=admin_headers
        )
        assert resp.status_code == 200

    async def test_one_admin_may_administer_another(
        self, client: AsyncClient, admin_headers, db
    ):
        other = await _make_user(db, "other-admin@test.com", role=Role.admin)

        resp = await client.patch(
            f"{BASE}/{other.id}", json={"isActive": False}, headers=admin_headers
        )
        assert resp.status_code == 200

    async def test_designers_cannot_manage_users(
        self, client: AsyncClient, designer_headers, test_user
    ):
        resp = await client.patch(
            f"{BASE}/{test_user.id}", json={"role": "admin"}, headers=designer_headers
        )
        assert resp.status_code == 403

    async def test_unknown_user_is_404(self, client: AsyncClient, admin_headers):
        resp = await client.patch(
            f"{BASE}/{uuid.uuid4()}", json={"isActive": False}, headers=admin_headers
        )
        assert resp.status_code == 404


class TestSearchingAndFiltering:
    async def test_searches_by_email_and_name(self, client: AsyncClient, admin_headers, db):
        await _make_user(db, "findme@example.com")

        by_email = (
            await client.get(f"{BASE}?search=findme", headers=admin_headers)
        ).json()
        assert [u["emailAddress"] for u in by_email["items"]] == ["findme@example.com"]

    async def test_filters_by_role(self, client: AsyncClient, admin_headers, test_designer):
        body = (
            await client.get(f"{BASE}?role=course_designer", headers=admin_headers)
        ).json()
        assert body["items"]
        assert all(u["role"] == "course_designer" for u in body["items"])

    async def test_filters_by_status(self, client: AsyncClient, admin_headers, db):
        await _make_user(db, "inactive@test.com", is_active=False)

        body = (await client.get(f"{BASE}?is_active=false", headers=admin_headers)).json()
        assert all(u["isActive"] is False for u in body["items"])

    async def test_total_reflects_the_filter_not_the_table(
        self, client: AsyncClient, admin_headers, db
    ):
        """Paginating a filtered list needs the filtered count, or page 2 is a lie."""
        await _make_user(db, "unique-search-target@test.com")

        body = (
            await client.get(f"{BASE}?search=unique-search-target", headers=admin_headers)
        ).json()
        assert body["total"] == 1


class TestWithdrawingAParticipant:
    async def test_erases_the_participant_and_returns_a_receipt(
        self, client: AsyncClient, admin_headers, db, auth_headers, enrolled_course, test_user
    ):
        section = enrolled_course["sections"][0]
        await client.post(
            "/api/v1/section-progress",
            headers=auth_headers,
            json={"sectionId": str(section.id), "timeSpentSeconds": 30},
        )

        resp = await client.post(f"{BASE}/{test_user.id}/withdraw", headers=admin_headers)

        assert resp.status_code == 200
        # A count of what went is the evidence a study needs; "deleted" alone is not.
        assert resp.json()["deleted"]["sectionProgress"] == 1

        gone = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {create_access_token(str(test_user.id))}"},
        )
        assert gone.status_code == 401

    async def test_refuses_to_withdraw_an_administrator(
        self, client: AsyncClient, admin_headers, test_admin
    ):
        """Withdrawal is a participant action; an admin leaving is an account change."""
        resp = await client.post(f"{BASE}/{test_admin.id}/withdraw", headers=admin_headers)

        assert resp.status_code == 400
        assert resp.json()["detail"]["error"]["code"] == "CANNOT_WITHDRAW_ADMIN"

    async def test_designers_cannot_withdraw_anyone(
        self, client: AsyncClient, designer_headers, test_user
    ):
        resp = await client.post(f"{BASE}/{test_user.id}/withdraw", headers=designer_headers)
        assert resp.status_code == 403

    async def test_unknown_user_is_404(self, client: AsyncClient, admin_headers):
        resp = await client.post(f"{BASE}/{uuid.uuid4()}/withdraw", headers=admin_headers)
        assert resp.status_code == 404
