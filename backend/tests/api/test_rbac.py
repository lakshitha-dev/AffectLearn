"""RBAC endpoint tests."""

from httpx import AsyncClient

from app.core.security import create_access_token
from app.db.seed import seed_accounts


# --- Admin /users endpoint ---


async def test_admin_list_users_success(test_client: AsyncClient, test_admin):
    token = create_access_token(str(test_admin.id))
    response = await test_client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


async def test_admin_list_users_forbidden_for_designer(test_client: AsyncClient, test_designer):
    token = create_access_token(str(test_designer.id))
    response = await test_client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["detail"]["error"]["code"] == "FORBIDDEN"


async def test_admin_list_users_forbidden_for_learner(test_client: AsyncClient, test_user):
    token = create_access_token(str(test_user.id))
    response = await test_client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_admin_list_users_unauthorized_no_token(test_client: AsyncClient):
    response = await test_client.get("/api/v1/admin/users")
    assert response.status_code == 401


# --- Analytics /courses endpoint ---


async def test_analytics_courses_success_for_designer(test_client: AsyncClient, test_designer):
    token = create_access_token(str(test_designer.id))
    response = await test_client.get(
        "/api/v1/analytics/courses",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


async def test_analytics_courses_success_for_admin(test_client: AsyncClient, test_admin):
    token = create_access_token(str(test_admin.id))
    response = await test_client.get(
        "/api/v1/analytics/courses",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


async def test_analytics_courses_forbidden_for_learner(test_client: AsyncClient, test_user):
    token = create_access_token(str(test_user.id))
    response = await test_client.get(
        "/api/v1/analytics/courses",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_analytics_courses_unauthorized_no_token(test_client: AsyncClient):
    response = await test_client.get("/api/v1/analytics/courses")
    assert response.status_code == 401


# --- Seed script ---


async def test_seed_creates_accounts(db_session):
    created = await seed_accounts(db_session)
    assert "designer@affectlearn.io" in created
    assert "admin@affectlearn.io" in created


async def test_seed_is_idempotent(db_session):
    await seed_accounts(db_session)
    created_again = await seed_accounts(db_session)
    assert len(created_again) == 0


# --- /auth/me returns role ---


async def test_me_returns_role(test_client: AsyncClient, test_designer):
    token = create_access_token(str(test_designer.id))
    response = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "course_designer"
