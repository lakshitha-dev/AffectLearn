"""RBAC endpoint tests."""

from httpx import AsyncClient

from app.core.security import create_access_token
from app.db.seed import seed_accounts


# --- Admin /users endpoint ---


async def test_admin_list_users_success(client: AsyncClient, test_admin):
    token = create_access_token(str(test_admin.id))
    response = await client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


async def test_admin_list_users_forbidden_for_designer(client: AsyncClient, test_designer):
    token = create_access_token(str(test_designer.id))
    response = await client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["detail"]["error"]["code"] == "FORBIDDEN"


async def test_admin_list_users_forbidden_for_learner(client: AsyncClient, test_user):
    token = create_access_token(str(test_user.id))
    response = await client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_admin_list_users_unauthorized_no_token(client: AsyncClient):
    response = await client.get("/api/v1/admin/users")
    assert response.status_code == 401


# --- Admin create-designer endpoint ---


async def test_admin_create_designer_success(client: AsyncClient, test_admin):
    token = create_access_token(str(test_admin.id))
    response = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"emailAddress": "new.designer@example.com", "firstName": "New", "lastName": "Designer"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "course_designer"
    assert data["emailVerified"] is True
    assert data["emailAddress"] == "new.designer@example.com"


async def test_admin_create_designer_duplicate_email(client: AsyncClient, test_admin, test_user):
    token = create_access_token(str(test_admin.id))
    response = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"emailAddress": "learner@test.com", "firstName": "Dup", "lastName": "User"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "DUPLICATE_EMAIL"


async def test_admin_create_designer_forbidden_for_designer(client: AsyncClient, test_designer):
    token = create_access_token(str(test_designer.id))
    response = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"emailAddress": "x@example.com", "firstName": "X", "lastName": "Y"},
    )
    assert response.status_code == 403


async def test_admin_create_designer_forbidden_for_learner(client: AsyncClient, test_user):
    token = create_access_token(str(test_user.id))
    response = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"emailAddress": "x@example.com", "firstName": "X", "lastName": "Y"},
    )
    assert response.status_code == 403


# --- Admin create-user (with password + role) endpoint ---


async def test_admin_create_user_success_each_role(client: AsyncClient, test_admin):
    token = create_access_token(str(test_admin.id))
    for role in ("learner", "course_designer", "admin"):
        response = await client.post(
            "/api/v1/admin/users/create",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "emailAddress": f"created.{role}@example.com",
                "firstName": "Made",
                "lastName": role.title(),
                "password": "Password1!",
                "role": role,
            },
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["role"] == role
        assert data["isActive"] is True
        assert data["emailVerified"] is True


async def test_admin_created_user_can_log_in(client: AsyncClient, test_admin):
    token = create_access_token(str(test_admin.id))
    create = await client.post(
        "/api/v1/admin/users/create",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "emailAddress": "loginable@example.com",
            "firstName": "Can",
            "lastName": "Login",
            "password": "Password1!",
            "role": "learner",
        },
    )
    assert create.status_code == 201
    login = await client.post(
        "/api/v1/auth/login",
        json={"emailAddress": "loginable@example.com", "password": "Password1!"},
    )
    assert login.status_code == 200
    assert "accessToken" in login.json()


async def test_admin_create_user_duplicate_email(client: AsyncClient, test_admin, test_user):
    token = create_access_token(str(test_admin.id))
    response = await client.post(
        "/api/v1/admin/users/create",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "emailAddress": "learner@test.com",
            "firstName": "Dup",
            "lastName": "User",
            "password": "Password1!",
            "role": "learner",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "DUPLICATE_EMAIL"


async def test_admin_create_user_weak_password_rejected(client: AsyncClient, test_admin):
    token = create_access_token(str(test_admin.id))
    response = await client.post(
        "/api/v1/admin/users/create",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "emailAddress": "weak@example.com",
            "firstName": "Weak",
            "lastName": "Pass",
            "password": "weak",
            "role": "learner",
        },
    )
    assert response.status_code == 422


async def test_admin_create_user_forbidden_for_designer(client: AsyncClient, test_designer):
    token = create_access_token(str(test_designer.id))
    response = await client.post(
        "/api/v1/admin/users/create",
        headers={"Authorization": f"Bearer {token}"},
        json={"emailAddress": "x@example.com", "firstName": "X", "lastName": "Y", "password": "Password1!", "role": "learner"},
    )
    assert response.status_code == 403


async def test_admin_create_user_unauthorized_no_token(client: AsyncClient):
    response = await client.post(
        "/api/v1/admin/users/create",
        json={"emailAddress": "x@example.com", "firstName": "X", "lastName": "Y", "password": "Password1!", "role": "learner"},
    )
    assert response.status_code == 401


# --- Admin edit-role endpoint ---


async def test_admin_update_role_success(client: AsyncClient, test_admin, test_user):
    token = create_access_token(str(test_admin.id))
    response = await client.patch(
        f"/api/v1/admin/users/{test_user.id}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "course_designer"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "course_designer"
    # Reflected in the list
    listing = await client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    match = next(u for u in listing.json()["items"] if u["id"] == str(test_user.id))
    assert match["role"] == "course_designer"


async def test_admin_update_role_not_found(client: AsyncClient, test_admin):
    token = create_access_token(str(test_admin.id))
    response = await client.patch(
        "/api/v1/admin/users/00000000-0000-0000-0000-000000000009/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "admin"},
    )
    assert response.status_code == 404


async def test_admin_update_role_forbidden_for_learner(client: AsyncClient, test_user):
    token = create_access_token(str(test_user.id))
    response = await client.patch(
        f"/api/v1/admin/users/{test_user.id}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "admin"},
    )
    assert response.status_code == 403


async def test_admin_cannot_change_own_role(client: AsyncClient, test_admin):
    token = create_access_token(str(test_admin.id))
    response = await client.patch(
        f"/api/v1/admin/users/{test_admin.id}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "learner"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "SELF_ROLE_CHANGE"


async def test_admin_can_demote_other_admin_when_not_last(client: AsyncClient, test_admin):
    """With two admins, demoting the OTHER one is allowed (self stays admin)."""
    token = create_access_token(str(test_admin.id))
    created = await client.post(
        "/api/v1/admin/users/create",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "emailAddress": "second.admin@example.com",
            "firstName": "Second",
            "lastName": "Admin",
            "password": "Password1!",
            "role": "admin",
        },
    )
    assert created.status_code == 201
    second_id = created.json()["id"]
    demote = await client.patch(
        f"/api/v1/admin/users/{second_id}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "learner"},
    )
    assert demote.status_code == 200
    assert demote.json()["role"] == "learner"


# --- Admin activate/deactivate endpoint ---


async def test_admin_deactivate_blocks_login(client: AsyncClient, test_admin, test_user):
    token = create_access_token(str(test_admin.id))
    # Deactivate the learner
    deactivate = await client.patch(
        f"/api/v1/admin/users/{test_user.id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"isActive": False},
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["isActive"] is False
    # Learner can no longer log in
    login = await client.post(
        "/api/v1/auth/login",
        json={"emailAddress": "learner@test.com", "password": "Password1!"},
    )
    assert login.status_code == 401
    # Reactivate restores access
    reactivate = await client.patch(
        f"/api/v1/admin/users/{test_user.id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"isActive": True},
    )
    assert reactivate.status_code == 200
    login2 = await client.post(
        "/api/v1/auth/login",
        json={"emailAddress": "learner@test.com", "password": "Password1!"},
    )
    assert login2.status_code == 200


async def test_admin_cannot_deactivate_self(client: AsyncClient, test_admin):
    token = create_access_token(str(test_admin.id))
    response = await client.patch(
        f"/api/v1/admin/users/{test_admin.id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"isActive": False},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "SELF_DEACTIVATION"


async def test_admin_update_status_forbidden_for_designer(client: AsyncClient, test_designer, test_user):
    token = create_access_token(str(test_designer.id))
    response = await client.patch(
        f"/api/v1/admin/users/{test_user.id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"isActive": False},
    )
    assert response.status_code == 403


# --- Admin search + last-login ---


async def test_admin_search_filters_by_name_and_email(client: AsyncClient, test_admin, test_user, test_designer):
    token = create_access_token(str(test_admin.id))
    # By name
    by_name = await client.get(
        "/api/v1/admin/users?search=Learner",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert by_name.status_code == 200
    emails = {u["emailAddress"] for u in by_name.json()["items"]}
    assert "learner@test.com" in emails
    assert "designer@test.com" not in emails
    # By email fragment
    by_email = await client.get(
        "/api/v1/admin/users?search=designer@test",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert by_email.json()["total"] == 1
    assert by_email.json()["items"][0]["emailAddress"] == "designer@test.com"


async def test_admin_search_escapes_like_wildcards(client: AsyncClient, test_admin, test_user, test_designer):
    """A bare '%' / '_' must be treated literally, not as a wildcard matching everyone."""
    token = create_access_token(str(test_admin.id))
    for term in ("%", "_"):
        response = await client.get(
            f"/api/v1/admin/users?search={term}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        # No seeded user has a literal % or _ in their name/email, so this matches none —
        # NOT the whole table (which is what an unescaped wildcard would return).
        assert response.json()["total"] == 0


async def test_admin_user_stats(client: AsyncClient, test_admin, test_user, test_designer):
    token = create_access_token(str(test_admin.id))
    response = await client.get(
        "/api/v1/admin/users/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["learners"] == 1
    assert data["courseDesigners"] == 1
    assert data["admins"] == 1
    assert data["verified"] == 3
    assert data["active"] == 3


async def test_admin_user_stats_forbidden_for_designer(client: AsyncClient, test_designer):
    token = create_access_token(str(test_designer.id))
    response = await client.get(
        "/api/v1/admin/users/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_admin_user_stats_unauthorized_no_token(client: AsyncClient):
    response = await client.get("/api/v1/admin/users/stats")
    assert response.status_code == 401


async def test_login_sets_last_login_and_surfaces_in_admin(client: AsyncClient, test_admin, test_user):
    admin_token = create_access_token(str(test_admin.id))
    # Before login, last login is null
    before = await client.get(
        f"/api/v1/admin/users?search={test_user.email_address}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert before.json()["items"][0]["lastLoginAt"] is None
    # Learner logs in
    login = await client.post(
        "/api/v1/auth/login",
        json={"emailAddress": "learner@test.com", "password": "Password1!"},
    )
    assert login.status_code == 200
    # Now last login is populated
    after = await client.get(
        f"/api/v1/admin/users?search={test_user.email_address}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert after.json()["items"][0]["lastLoginAt"] is not None


# --- Analytics endpoint RBAC (course overview) ---
# Role-gating only: a random course id is fine — the role check runs before the
# 404, so designer/admin pass the gate (200/404) while a learner is rejected (403).

_ANALYTICS_OVERVIEW = "/api/v1/analytics/courses/00000000-0000-0000-0000-000000000001/overview"


async def test_analytics_overview_allowed_for_designer(client: AsyncClient, test_designer):
    token = create_access_token(str(test_designer.id))
    response = await client.get(
        _ANALYTICS_OVERVIEW,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code not in (401, 403)


async def test_analytics_overview_allowed_for_admin(client: AsyncClient, test_admin):
    token = create_access_token(str(test_admin.id))
    response = await client.get(
        _ANALYTICS_OVERVIEW,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code not in (401, 403)


async def test_analytics_overview_forbidden_for_learner(client: AsyncClient, test_user):
    token = create_access_token(str(test_user.id))
    response = await client.get(
        _ANALYTICS_OVERVIEW,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_analytics_overview_unauthorized_no_token(client: AsyncClient):
    response = await client.get(_ANALYTICS_OVERVIEW)
    assert response.status_code == 401


# --- Seed script ---


async def test_seed_creates_accounts(db):
    created = await seed_accounts(db)
    assert "designer@affectlearn.io" in created
    assert "admin@affectlearn.io" in created


async def test_seed_is_idempotent(db):
    await seed_accounts(db)
    created_again = await seed_accounts(db)
    assert len(created_again) == 0


# --- /auth/me returns role ---


async def test_me_returns_role(client: AsyncClient, test_designer):
    token = create_access_token(str(test_designer.id))
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "course_designer"
