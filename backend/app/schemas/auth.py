"""Auth request/response schemas."""

import re
import uuid
from typing import Literal

from pydantic import EmailStr, Field, field_validator

from app.schemas.base import CamelModel

_PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]).{8,}$"
)


def _validate_password_complexity(v: str) -> str:
    if not _PASSWORD_PATTERN.match(v):
        raise ValueError(
            "Password must contain at least one uppercase letter, "
            "one lowercase letter, one digit, and one special character"
        )
    return v


class RegisterRequest(CamelModel):
    email_address: EmailStr
    password: str = Field(min_length=8)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    age_range: str | None = None
    degree_program: str | None = None
    # Optional shared secret to self-register as a course designer (see DESIGNER_INVITE_CODE).
    designer_invite_code: str | None = None

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)


class LoginRequest(CamelModel):
    email_address: EmailStr
    password: str


class TokenResponse(CamelModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(CamelModel):
    refresh_token: str


class UserResponse(CamelModel):
    id: uuid.UUID
    email_address: str
    first_name: str
    last_name: str
    role: Literal["learner", "course_designer", "admin"]
    age_range: str | None = None
    degree_program: str | None = None
    consent_given_at: str | None = None
    webcam_enabled: bool = False


class ProfileUpdateRequest(CamelModel):
    """Editable profile fields.

    Deliberately excludes `email_address` and `role`. Email is the login identifier and changing
    it needs the same verification round-trip registration does, so it is not a profile edit;
    role is an administrative decision and belongs behind the admin endpoints, not behind a form
    the account holder controls.

    Every field is optional so a caller may send only what changed, but a field that IS sent must
    be valid — `first_name: ""` is rejected rather than quietly blanking the name.
    """

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    age_range: str | None = Field(default=None, max_length=20)
    degree_program: str | None = Field(default=None, max_length=200)


class ConsentRequest(CamelModel):
    consent_given: Literal[True]


class WebcamModeRequest(CamelModel):
    webcam_enabled: bool


class MessageResponse(CamelModel):
    message: str


class VerifyEmailRequest(CamelModel):
    token: str


class ResendVerificationRequest(CamelModel):
    email_address: EmailStr


class ForgotPasswordRequest(CamelModel):
    email_address: EmailStr


class ResetPasswordRequest(CamelModel):
    token: str
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)


class CreateDesignerRequest(CamelModel):
    """Admin-supplied details for a new course-designer account (no password — the
    designer sets it via an emailed link)."""
    email_address: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)


class AdminUserItem(CamelModel):
    """Richer user row for the admin console (adds status + timestamps)."""
    id: uuid.UUID
    email_address: str
    first_name: str
    last_name: str
    role: Literal["learner", "course_designer", "admin"]
    is_active: bool
    email_verified: bool
    created_at: str | None = None


class ChangePasswordRequest(CamelModel):
    """Change the password of the signed-in account.

    The current password is required even though the caller is already authenticated: an access
    token can be left behind on a shared machine, and a password change is the one action that
    locks the real owner out of their own account.
    """

    current_password: str
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def _complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)


class DeleteAccountRequest(CamelModel):
    """Erase this account and everything recorded about it.

    The password is required because this is irreversible. `confirm` must be the literal string
    DELETE: a single boolean is too easy to send by accident from a half-written client, and this
    endpoint destroys a participant's entire record.
    """

    password: str
    confirm: str


class ErasureReceipt(CamelModel):
    """What erasure actually removed, per table.

    Returned rather than a bare 204 so a participant who asked for deletion gets something they
    can keep. "Deleted" with no numbers is indistinguishable from a no-op that returned 200.
    """

    deleted: dict[str, int]
