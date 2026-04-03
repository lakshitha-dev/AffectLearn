"""Auth API endpoints: register, login, refresh, me."""

import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import Role, User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check for duplicate email
    result = await db.execute(select(User).where(User.email_address == body.email_address))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "DUPLICATE_EMAIL", "message": "Already have an account? Sign in"}},
        )

    user = User(
        email_address=body.email_address,
        password_hash=hash_password(body.password),
        first_name=body.first_name,
        last_name=body.last_name,
        role=Role.learner,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email_address == body.email_address))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password"}},
        )

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid token type"}},
            )
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid or expired refresh token"}},
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

    new_access_token = create_access_token(str(user.id))

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=body.refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        email_address=current_user.email_address,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        role=current_user.role.value,
    )
