"""Auth endpoint tests."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token


# --- Registration Tests ---


async def test_register_success(test_client: AsyncClient):
    response = await test_client.post(
        "/api/v1/auth/register",
        json={
            "emailAddress": "new@example.com",
            "password": "StrongPass1!",
            "firstName": "Jane",
            "lastName": "Doe",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "accessToken" in data
    assert "refreshToken" in data
    assert data["tokenType"] == "bearer"
    assert data["expiresIn"] == 1800  # 30 min * 60


async def test_register_duplicate_email(test_client: AsyncClient, test_user):
    response = await test_client.post(
        "/api/v1/auth/register",
        json={
            "emailAddress": "learner@test.com",
            "password": "StrongPass1!",
            "firstName": "Dupe",
            "lastName": "User",
        },
    )
    assert response.status_code == 409
    data = response.json()
    assert data["detail"]["error"]["code"] == "DUPLICATE_EMAIL"


async def test_register_invalid_email(test_client: AsyncClient):
    response = await test_client.post(
        "/api/v1/auth/register",
        json={
            "emailAddress": "not-an-email",
            "password": "StrongPass1!",
            "firstName": "Bad",
            "lastName": "Email",
        },
    )
    assert response.status_code == 422


async def test_register_weak_password(test_client: AsyncClient):
    response = await test_client.post(
        "/api/v1/auth/register",
        json={
            "emailAddress": "weak@example.com",
            "password": "short",
            "firstName": "Weak",
            "lastName": "Pass",
        },
    )
    assert response.status_code == 422


async def test_register_password_missing_complexity(test_client: AsyncClient):
    # Long enough but missing uppercase, digit, and special character
    response = await test_client.post(
        "/api/v1/auth/register",
        json={
            "emailAddress": "nocomplexity@example.com",
            "password": "alllowercase",
            "firstName": "No",
            "lastName": "Complexity",
        },
    )
    assert response.status_code == 422


# --- Login Tests ---


async def test_login_success(test_client: AsyncClient, test_user):
    response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "emailAddress": "learner@test.com",
            "password": "TestPass123!",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "accessToken" in data
    assert "refreshToken" in data
    assert data["tokenType"] == "bearer"


async def test_login_invalid_credentials(test_client: AsyncClient, test_user):
    response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "emailAddress": "learner@test.com",
            "password": "WrongPassword!",
        },
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_user_not_found(test_client: AsyncClient):
    response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "emailAddress": "noone@example.com",
            "password": "SomePass123!",
        },
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_inactive_user_rejected(test_client: AsyncClient, db_session: AsyncSession):
    from app.models.user import Role, User
    from app.core.security import hash_password

    inactive_user = User(
        email_address="inactive@test.com",
        password_hash=hash_password("TestPass123!"),
        first_name="Inactive",
        last_name="User",
        role=Role.learner,
        is_active=False,
    )
    db_session.add(inactive_user)
    await db_session.commit()

    response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "emailAddress": "inactive@test.com",
            "password": "TestPass123!",
        },
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "INVALID_CREDENTIALS"


# --- Token Refresh Tests ---


async def test_token_refresh(test_client: AsyncClient, test_user):
    refresh_token = create_refresh_token(str(test_user.id))
    response = await test_client.post(
        "/api/v1/auth/refresh",
        json={"refreshToken": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "accessToken" in data
    assert "refreshToken" in data
    # Verify the returned refresh token is a valid JWT for this user
    from app.core.security import decode_token
    payload = decode_token(data["refreshToken"])
    assert payload["sub"] == str(test_user.id)
    assert payload["type"] == "refresh"


async def test_wrong_token_type_rejected(test_client: AsyncClient):
    # Use an access token as refresh token — should be rejected (wrong type)
    fake_token = create_access_token("some-user-id")
    response = await test_client.post(
        "/api/v1/auth/refresh",
        json={"refreshToken": fake_token},
    )
    assert response.status_code == 401


async def test_expired_token_rejected(test_client: AsyncClient):
    expired_payload = {
        "sub": "some-user-id",
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "type": "refresh",
    }
    expired_token = jwt.encode(expired_payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    response = await test_client.post(
        "/api/v1/auth/refresh",
        json={"refreshToken": expired_token},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "INVALID_TOKEN"


async def test_protected_route_without_token(test_client: AsyncClient):
    response = await test_client.get("/api/v1/auth/me")
    assert response.status_code == 401


# --- Me Endpoint Tests ---


async def test_me_endpoint_returns_current_user(test_client: AsyncClient, test_user):
    token = create_access_token(str(test_user.id))
    response = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["emailAddress"] == "learner@test.com"
    assert data["firstName"] == "Test"
    assert data["lastName"] == "Learner"
    assert data["role"] == "learner"
