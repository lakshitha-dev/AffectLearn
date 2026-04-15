"""Auth request/response schemas."""

import re
import uuid
from typing import Literal

from pydantic import EmailStr, Field, field_validator

from app.schemas.base import CamelModel

_PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]).{8,}$"
)


class RegisterRequest(CamelModel):
    email_address: EmailStr
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if not _PASSWORD_PATTERN.match(v):
            raise ValueError(
                "Password must contain at least one uppercase letter, "
                "one lowercase letter, one digit, and one special character"
            )
        return v
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    age_range: str | None = None
    degree_program: str | None = None


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
