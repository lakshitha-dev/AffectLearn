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
