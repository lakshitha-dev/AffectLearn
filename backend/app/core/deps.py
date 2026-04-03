"""Dependency injection for FastAPI routes."""

import uuid as uuid_mod
from collections.abc import AsyncGenerator, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import async_session
from app.models.user import Role, User

bearer_scheme = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate JWT from Authorization header, return the current user."""
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid token type"}},
            )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"code": "INVALID_TOKEN", "message": "Token missing subject"}},
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Could not validate credentials"}},
        )

    try:
        uid = uuid_mod.UUID(user_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid token subject"}},
        )

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "User not found or inactive"}},
        )

    return user


def require_role(*roles: Role) -> Callable:
    """Factory that returns a dependency requiring the current user to have one of the specified roles."""

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "FORBIDDEN", "message": "Insufficient permissions"}},
            )
        return current_user

    return role_checker
