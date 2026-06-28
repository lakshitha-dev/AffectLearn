"""Admin API endpoints."""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db, require_role
from app.core.security import generate_url_token, hash_password, hash_url_token
from app.models.email_token import PASSWORD_RESET, EmailToken
from app.models.user import Role, User
from app.schemas.auth import AdminUserItem, CreateDesignerRequest
from app.schemas.base import PaginatedResponse
from app.services.email_service import send_designer_invite_email

router = APIRouter()


def _to_item(u: User) -> AdminUserItem:
    return AdminUserItem(
        id=u.id,
        email_address=u.email_address,
        first_name=u.first_name,
        last_name=u.last_name,
        role=u.role.value,
        is_active=u.is_active,
        email_verified=u.email_verified,
        created_at=u.created_at.isoformat() if u.created_at else None,
    )


@router.get("/users", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List all users. Requires admin role."""
    offset = (page - 1) * page_size

    total_result = await db.execute(select(func.count()).select_from(User))
    total = total_result.scalar_one()

    result = await db.execute(
        select(User).offset(offset).limit(page_size).order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    return PaginatedResponse(
        items=[_to_item(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/users", response_model=AdminUserItem, status_code=status.HTTP_201_CREATED)
async def create_designer(
    body: CreateDesignerRequest,
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Create a course-designer account (admin only). The account is created verified and
    active with an unusable random password; the designer sets their own password via an
    emailed link (reuses the password-reset flow)."""
    existing = await db.execute(select(User).where(User.email_address == body.email_address))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "DUPLICATE_EMAIL", "message": "A user with that email already exists"}},
        )

    user = User(
        email_address=body.email_address,
        password_hash=hash_password(secrets.token_urlsafe(32)),  # unusable until they set one
        first_name=body.first_name,
        last_name=body.last_name,
        role=Role.course_designer,
        is_active=True,
        email_verified=True,  # admin-created accounts are trusted
    )
    db.add(user)
    await db.flush()

    # Set-password link: reuse the password-reset token + page, with a generous 24h window.
    raw_token = generate_url_token()
    db.add(
        EmailToken(
            user_id=user.id,
            token_hash=hash_url_token(raw_token),
            purpose=PASSWORD_RESET,
            expires_at=datetime.now(timezone.utc)
            + timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS),
        )
    )
    await db.commit()
    await db.refresh(user)

    link = f"{settings.FRONTEND_BASE_URL}/reset-password?token={raw_token}"
    await send_designer_invite_email(user.email_address, user.first_name, link)

    return _to_item(user)
