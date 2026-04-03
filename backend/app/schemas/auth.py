"""Auth request/response schemas."""

import uuid

from pydantic import EmailStr, Field

from app.schemas.base import CamelModel


class RegisterRequest(CamelModel):
    email_address: EmailStr
    password: str = Field(min_length=8)
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
    role: str
