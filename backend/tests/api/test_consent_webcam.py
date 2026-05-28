"""Tests for consent and webcam-mode auth endpoints."""

import pytest
from httpx import AsyncClient


CONSENT_URL = "/api/v1/auth/consent"
WEBCAM_URL = "/api/v1/auth/webcam-mode"


class TestConsentEndpoint:
    """POST /api/v1/auth/consent — learner-only, idempotent."""

    async def test_happy_path_returns_200_and_sets_consent_at(
        self, client: AsyncClient, test_user, auth_headers
    ):
        """Learner POSTing consentGiven=true receives 200 with consentGivenAt populated."""
        resp = await client.post(
            CONSENT_URL,
            json={"consentGiven": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["consentGivenAt"] is not None

    async def test_response_contains_user_fields(
        self, client: AsyncClient, test_user, auth_headers
    ):
        """Response body is a full UserResponse with expected fields."""
        resp = await client.post(
            CONSENT_URL,
            json={"consentGiven": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["emailAddress"] == test_user.email_address
        assert data["role"] == "learner"

    async def test_idempotent_second_call_returns_200(
        self, client: AsyncClient, test_user, auth_headers
    ):
        """Calling the endpoint twice both return 200."""
        resp1 = await client.post(
            CONSENT_URL, json={"consentGiven": True}, headers=auth_headers
        )
        resp2 = await client.post(
            CONSENT_URL, json={"consentGiven": True}, headers=auth_headers
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200

    async def test_idempotent_does_not_overwrite_consent_timestamp(
        self, client: AsyncClient, test_user, auth_headers
    ):
        """Second POST must not change the original consentGivenAt timestamp."""
        resp1 = await client.post(
            CONSENT_URL, json={"consentGiven": True}, headers=auth_headers
        )
        original_ts = resp1.json()["consentGivenAt"]

        resp2 = await client.post(
            CONSENT_URL, json={"consentGiven": True}, headers=auth_headers
        )
        second_ts = resp2.json()["consentGivenAt"]

        assert original_ts == second_ts

    async def test_reject_consent_false_returns_422(
        self, client: AsyncClient, auth_headers
    ):
        """Schema uses Literal[True], so consentGiven=false must be rejected with 422."""
        resp = await client.post(
            CONSENT_URL,
            json={"consentGiven": False},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_missing_body_field_returns_422(
        self, client: AsyncClient, auth_headers
    ):
        """Request body without the required field must be rejected."""
        resp = await client.post(CONSENT_URL, json={}, headers=auth_headers)
        assert resp.status_code == 422

    async def test_designer_role_returns_403(
        self, client: AsyncClient, test_designer, designer_headers
    ):
        """Course designers do not have access to this learner-only endpoint."""
        resp = await client.post(
            CONSENT_URL,
            json={"consentGiven": True},
            headers=designer_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"]["code"] == "FORBIDDEN"

    async def test_admin_role_returns_403(
        self, client: AsyncClient, test_admin, admin_headers
    ):
        """Admins do not have access to this learner-only endpoint."""
        resp = await client.post(
            CONSENT_URL,
            json={"consentGiven": True},
            headers=admin_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"]["code"] == "FORBIDDEN"

    async def test_unauthenticated_returns_401_or_403(
        self, client: AsyncClient
    ):
        """Missing auth token must be rejected (HTTPBearer returns 403; some versions 401)."""
        resp = await client.post(CONSENT_URL, json={"consentGiven": True})
        assert resp.status_code in (401, 403)


class TestWebcamModeEndpoint:
    """POST /api/v1/auth/webcam-mode — learner-only, toggleable."""

    async def test_set_enabled_true_returns_200(
        self, client: AsyncClient, test_user, auth_headers
    ):
        """Learner enabling webcam receives 200 with webcamEnabled=true."""
        resp = await client.post(
            WEBCAM_URL,
            json={"webcamEnabled": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["webcamEnabled"] is True

    async def test_set_enabled_false_returns_200(
        self, client: AsyncClient, test_user, auth_headers
    ):
        """Learner disabling webcam receives 200 with webcamEnabled=false."""
        resp = await client.post(
            WEBCAM_URL,
            json={"webcamEnabled": False},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["webcamEnabled"] is False

    async def test_toggle_true_then_false(
        self, client: AsyncClient, test_user, auth_headers
    ):
        """Setting true then false produces the correct final state on each call."""
        r1 = await client.post(
            WEBCAM_URL, json={"webcamEnabled": True}, headers=auth_headers
        )
        assert r1.status_code == 200
        assert r1.json()["webcamEnabled"] is True

        r2 = await client.post(
            WEBCAM_URL, json={"webcamEnabled": False}, headers=auth_headers
        )
        assert r2.status_code == 200
        assert r2.json()["webcamEnabled"] is False

    async def test_toggle_false_then_true(
        self, client: AsyncClient, test_user, auth_headers
    ):
        """Setting false then true produces the correct final state on each call."""
        r1 = await client.post(
            WEBCAM_URL, json={"webcamEnabled": False}, headers=auth_headers
        )
        assert r1.status_code == 200
        assert r1.json()["webcamEnabled"] is False

        r2 = await client.post(
            WEBCAM_URL, json={"webcamEnabled": True}, headers=auth_headers
        )
        assert r2.status_code == 200
        assert r2.json()["webcamEnabled"] is True

    async def test_response_contains_user_fields(
        self, client: AsyncClient, test_user, auth_headers
    ):
        """Response body is a full UserResponse with expected identity fields."""
        resp = await client.post(
            WEBCAM_URL,
            json={"webcamEnabled": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["emailAddress"] == test_user.email_address
        assert data["role"] == "learner"

    async def test_missing_body_field_returns_422(
        self, client: AsyncClient, auth_headers
    ):
        """Request body without webcamEnabled must be rejected."""
        resp = await client.post(WEBCAM_URL, json={}, headers=auth_headers)
        assert resp.status_code == 422

    async def test_designer_role_returns_403(
        self, client: AsyncClient, test_designer, designer_headers
    ):
        """Course designers do not have access to this learner-only endpoint."""
        resp = await client.post(
            WEBCAM_URL,
            json={"webcamEnabled": True},
            headers=designer_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"]["code"] == "FORBIDDEN"

    async def test_admin_role_returns_403(
        self, client: AsyncClient, test_admin, admin_headers
    ):
        """Admins do not have access to this learner-only endpoint."""
        resp = await client.post(
            WEBCAM_URL,
            json={"webcamEnabled": True},
            headers=admin_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"]["code"] == "FORBIDDEN"

    async def test_unauthenticated_returns_401_or_403(
        self, client: AsyncClient
    ):
        """Missing auth token must be rejected."""
        resp = await client.post(WEBCAM_URL, json={"webcamEnabled": True})
        assert resp.status_code in (401, 403)
