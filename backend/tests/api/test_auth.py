"""Auth endpoint tests."""

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token


# --- Registration Tests ---


async def test_register_success(client: AsyncClient):
    response = await client.post(
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
    # Registration no longer auto-logs-in — login is gated on email verification.
    assert "accessToken" not in data
    assert "message" in data


async def test_register_duplicate_email(client: AsyncClient, test_user):
    response = await client.post(
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


async def test_register_invalid_email(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "emailAddress": "not-an-email",
            "password": "StrongPass1!",
            "firstName": "Bad",
            "lastName": "Email",
        },
    )
    assert response.status_code == 422


async def test_register_weak_password(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "emailAddress": "weak@example.com",
            "password": "short",
            "firstName": "Weak",
            "lastName": "Pass",
        },
    )
    assert response.status_code == 422


async def test_register_password_missing_complexity(client: AsyncClient):
    # Long enough but missing uppercase, digit, and special character
    response = await client.post(
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


async def test_login_success(client: AsyncClient, test_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "emailAddress": "learner@test.com",
            "password": "Password1!",  # matches the test_user fixture hash
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "accessToken" in data
    assert "refreshToken" in data
    assert data["tokenType"] == "bearer"


async def test_login_invalid_credentials(client: AsyncClient, test_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "emailAddress": "learner@test.com",
            "password": "WrongPassword!",
        },
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_user_not_found(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "emailAddress": "noone@example.com",
            "password": "SomePass123!",
        },
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_inactive_user_rejected(client: AsyncClient, db: AsyncSession):
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
    db.add(inactive_user)
    await db.commit()

    response = await client.post(
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


async def test_token_refresh(client: AsyncClient, test_user):
    refresh_token = create_refresh_token(str(test_user.id))
    response = await client.post(
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


async def test_wrong_token_type_rejected(client: AsyncClient):
    # Use an access token as refresh token — should be rejected (wrong type)
    fake_token = create_access_token("some-user-id")
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refreshToken": fake_token},
    )
    assert response.status_code == 401


async def test_expired_token_rejected(client: AsyncClient):
    expired_payload = {
        "sub": "some-user-id",
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "type": "refresh",
    }
    expired_token = jwt.encode(expired_payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refreshToken": expired_token},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "INVALID_TOKEN"


async def test_protected_route_without_token(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


# --- Me Endpoint Tests ---


async def test_me_endpoint_returns_current_user(client: AsyncClient, test_user):
    token = create_access_token(str(test_user.id))
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["emailAddress"] == "learner@test.com"
    assert data["firstName"] == "Test"
    assert data["lastName"] == "Learner"
    assert data["role"] == "learner"


# --- Email Verification Tests ---


def _capture_link(monkeypatch, target: str) -> dict:
    """Monkeypatch an email sender in the auth route module to capture the emailed link."""
    captured: dict = {}

    async def fake_send(to: str, link: str) -> None:
        captured["to"] = to
        captured["link"] = link

    monkeypatch.setattr(f"app.api.routes.auth.{target}", fake_send)
    return captured


def _token_from(link: str) -> str:
    return link.split("token=", 1)[1]


async def _register(client: AsyncClient, email: str, **extra) -> None:
    payload = {
        "emailAddress": email,
        "password": "StrongPass1!",
        "firstName": "Jane",
        "lastName": "Doe",
        **extra,
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201


async def test_login_blocked_until_verified(client: AsyncClient):
    await _register(client, "unverified@example.com")
    resp = await client.post(
        "/api/v1/auth/login",
        json={"emailAddress": "unverified@example.com", "password": "StrongPass1!"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"]["code"] == "EMAIL_NOT_VERIFIED"


async def test_register_verify_then_login(client: AsyncClient, monkeypatch):
    captured = _capture_link(monkeypatch, "send_verification_email")
    await _register(client, "verifyme@example.com")

    token = _token_from(captured["link"])
    verify = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verify.status_code == 200
    assert "accessToken" in verify.json()  # auto-login after verifying

    login = await client.post(
        "/api/v1/auth/login",
        json={"emailAddress": "verifyme@example.com", "password": "StrongPass1!"},
    )
    assert login.status_code == 200
    assert "accessToken" in login.json()


async def test_verify_email_invalid_token(client: AsyncClient):
    resp = await client.post("/api/v1/auth/verify-email", json={"token": "not-a-real-token"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "INVALID_TOKEN"


async def test_verify_email_expired_token(client: AsyncClient, db, test_user):
    from datetime import datetime, timedelta, timezone

    from app.core.security import hash_url_token
    from app.models.email_token import EMAIL_VERIFICATION, EmailToken

    db.add(
        EmailToken(
            user_id=test_user.id,
            token_hash=hash_url_token("expired-raw-token"),
            purpose=EMAIL_VERIFICATION,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    await db.commit()

    resp = await client.post("/api/v1/auth/verify-email", json={"token": "expired-raw-token"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "TOKEN_EXPIRED"


async def test_resend_verification_is_generic(client: AsyncClient):
    # Unknown email still returns 200 (no user enumeration).
    resp = await client.post(
        "/api/v1/auth/resend-verification", json={"emailAddress": "nobody@example.com"}
    )
    assert resp.status_code == 200
    assert "message" in resp.json()


# --- Password Reset Tests ---


async def test_forgot_then_reset_password(client: AsyncClient, test_user, monkeypatch):
    captured = _capture_link(monkeypatch, "send_password_reset_email")
    forgot = await client.post(
        "/api/v1/auth/forgot-password", json={"emailAddress": "learner@test.com"}
    )
    assert forgot.status_code == 200

    token = _token_from(captured["link"])
    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "password": "BrandNew1!"},
    )
    assert reset.status_code == 200

    login = await client.post(
        "/api/v1/auth/login",
        json={"emailAddress": "learner@test.com", "password": "BrandNew1!"},
    )
    assert login.status_code == 200


async def test_reset_password_invalid_token(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "bogus", "password": "BrandNew1!"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "INVALID_TOKEN"


async def test_forgot_password_unknown_email_is_generic(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/forgot-password", json={"emailAddress": "ghost@example.com"}
    )
    assert resp.status_code == 200
    assert "message" in resp.json()


# --- Designer Invite Code Tests ---


async def test_register_designer_with_valid_code(client: AsyncClient, db, monkeypatch):
    from sqlalchemy import select

    from app.core.config import settings
    from app.models.user import Role, User

    monkeypatch.setattr(settings, "DESIGNER_INVITE_CODE", "LET-ME-IN")
    await _register(client, "designer-signup@example.com", designerInviteCode="LET-ME-IN")

    user = (
        await db.execute(select(User).where(User.email_address == "designer-signup@example.com"))
    ).scalar_one()
    assert user.role == Role.course_designer


async def test_register_designer_with_wrong_code(client: AsyncClient, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "DESIGNER_INVITE_CODE", "LET-ME-IN")
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "emailAddress": "imposter@example.com",
            "password": "StrongPass1!",
            "firstName": "Im",
            "lastName": "Poster",
            "designerInviteCode": "WRONG",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "INVALID_INVITE_CODE"


async def test_register_without_code_is_learner(client: AsyncClient, db):
    from sqlalchemy import select

    from app.models.user import Role, User

    await _register(client, "plain-learner@example.com")
    user = (
        await db.execute(select(User).where(User.email_address == "plain-learner@example.com"))
    ).scalar_one()
    assert user.role == Role.learner


# --- Change Password Tests ---


def _capture_notice(monkeypatch, target: str) -> dict:
    """Capture a single-argument notification email sent from the auth route module.

    Deliberately typed `to: str` and asserted against below. The production defect this guards
    passed the whole `User` object here; because `_send` swallows every exception, the failure
    surfaced only as a missing email in production and nothing failed in test or in the request.
    """
    captured: dict = {}

    async def fake_send(to: str) -> None:
        captured["to"] = to

    monkeypatch.setattr(f"app.api.routes.auth.{target}", fake_send)
    return captured


async def test_change_password_sends_notice_to_the_email_address(
    client: AsyncClient, test_user, monkeypatch
):
    """The confirmation must be addressed to the email STRING, not the User object.

    Regression test: `send_password_changed_email` takes `to: str`. Passing `current_user` made
    the address an ORM object, which the mail transport could not serialise; the error was
    swallowed and the security confirmation silently never sent.
    """
    captured = _capture_notice(monkeypatch, "send_password_changed_email")
    token = create_access_token(str(test_user.id))

    resp = await client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"currentPassword": "Password1!", "newPassword": "NewStrongPass1!"},
    )

    assert resp.status_code == 200
    assert captured["to"] == "learner@test.com"
    assert isinstance(captured["to"], str)


async def test_change_password_then_login_with_new_password(
    client: AsyncClient, test_user, monkeypatch
):
    _capture_notice(monkeypatch, "send_password_changed_email")
    token = create_access_token(str(test_user.id))

    resp = await client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"currentPassword": "Password1!", "newPassword": "NewStrongPass1!"},
    )
    assert resp.status_code == 200

    old = await client.post(
        "/api/v1/auth/login",
        json={"emailAddress": "learner@test.com", "password": "Password1!"},
    )
    assert old.status_code == 401

    new = await client.post(
        "/api/v1/auth/login",
        json={"emailAddress": "learner@test.com", "password": "NewStrongPass1!"},
    )
    assert new.status_code == 200


async def test_change_password_rejects_wrong_current_password(
    client: AsyncClient, test_user, monkeypatch
):
    captured = _capture_notice(monkeypatch, "send_password_changed_email")
    token = create_access_token(str(test_user.id))

    resp = await client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"currentPassword": "NotMyPassword1!", "newPassword": "NewStrongPass1!"},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "INVALID_CREDENTIALS"
    # No password changed means no security notice.
    assert captured == {}


async def test_change_password_requires_authentication(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/change-password",
        json={"currentPassword": "Password1!", "newPassword": "NewStrongPass1!"},
    )
    assert resp.status_code == 401


# --- Dev credentials exposure ---


class TestDevCredentialsAreNotReachableInProduction:
    """This route is unauthenticated and returns the seeded ADMIN password in plaintext.

    It had no tests at all, including none asserting it disappears in production. The flag alone
    was the only thing standing between a normal deployment and giving away admin credentials to
    anyone who knew the path, and a flag is exactly the kind of thing that travels in a copied
    `.env`. The environment check is the part that cannot be enabled by accident.
    """

    async def test_404_in_production_even_when_the_flag_is_on(
        self, client: AsyncClient, monkeypatch
    ):
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        monkeypatch.setattr(settings, "EXPOSE_DEV_CREDENTIALS", True)

        resp = await client.get("/api/v1/auth/dev-credentials")
        assert resp.status_code == 404

    async def test_404_when_the_flag_is_off(self, client: AsyncClient, monkeypatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", "development")
        monkeypatch.setattr(settings, "EXPOSE_DEV_CREDENTIALS", False)

        resp = await client.get("/api/v1/auth/dev-credentials")
        assert resp.status_code == 404

    async def test_available_in_development_when_explicitly_enabled(
        self, client: AsyncClient, monkeypatch
    ):
        monkeypatch.setattr(settings, "ENVIRONMENT", "development")
        monkeypatch.setattr(settings, "EXPOSE_DEV_CREDENTIALS", True)

        resp = await client.get("/api/v1/auth/dev-credentials")
        assert resp.status_code == 200
        assert "accounts" in resp.json()


# --- Profile update ---


class TestProfileUpdate:
    """`PATCH /auth/me` — the endpoint the designer settings page needed and did not have.

    Before this, a name mistyped at registration was permanent for every role, and the designer
    settings screen filled the gap with hardcoded placeholder details behind disabled inputs.
    """

    async def test_updates_only_the_fields_sent(self, client: AsyncClient, test_user):
        token = create_access_token(str(test_user.id))
        headers = {"Authorization": f"Bearer {token}"}

        seed = await client.patch(
            "/api/v1/auth/me",
            headers=headers,
            json={"firstName": "Ada", "lastName": "Lovelace", "degreeProgram": "Mathematics"},
        )
        assert seed.status_code == 200

        # A form submitting only the name must not blank the degree programme.
        resp = await client.patch(
            "/api/v1/auth/me", headers=headers, json={"firstName": "Grace"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["firstName"] == "Grace"
        assert body["lastName"] == "Lovelace"
        assert body["degreeProgram"] == "Mathematics"

    async def test_persists_across_requests(self, client: AsyncClient, test_user):
        headers = {"Authorization": f"Bearer {create_access_token(str(test_user.id))}"}
        await client.patch("/api/v1/auth/me", headers=headers, json={"firstName": "Grace"})

        me = await client.get("/api/v1/auth/me", headers=headers)
        assert me.json()["firstName"] == "Grace"

    async def test_cannot_change_email_or_role(self, client: AsyncClient, test_user):
        """Email is the login identifier and role is an administrative decision.

        Both are ignored rather than honoured — a profile form is not the place to grant
        yourself a different role.
        """
        headers = {"Authorization": f"Bearer {create_access_token(str(test_user.id))}"}

        resp = await client.patch(
            "/api/v1/auth/me",
            headers=headers,
            json={"emailAddress": "new@example.com", "role": "admin", "firstName": "Grace"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["emailAddress"] == "learner@test.com"
        assert body["role"] == "learner"

    async def test_rejects_a_blank_name(self, client: AsyncClient, test_user):
        headers = {"Authorization": f"Bearer {create_access_token(str(test_user.id))}"}
        resp = await client.patch("/api/v1/auth/me", headers=headers, json={"firstName": ""})
        assert resp.status_code == 422

    async def test_designer_can_update_their_own_profile(
        self, client: AsyncClient, test_designer
    ):
        headers = {"Authorization": f"Bearer {create_access_token(str(test_designer.id))}"}
        resp = await client.patch(
            "/api/v1/auth/me", headers=headers, json={"firstName": "Morgan"}
        )
        assert resp.status_code == 200
        assert resp.json()["firstName"] == "Morgan"

    async def test_requires_authentication(self, client: AsyncClient):
        resp = await client.patch("/api/v1/auth/me", json={"firstName": "Nobody"})
        assert resp.status_code == 401
