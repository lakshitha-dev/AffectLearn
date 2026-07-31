"""Admin API endpoints."""

import secrets
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db, require_role
from app.core.security import generate_url_token, hash_password, hash_url_token
from app.models.email_token import PASSWORD_RESET, EmailToken
from app.models.user import Role, User
from app.schemas.auth import (
    AdminUserItem,
    CreateDesignerRequest,
    CreateUserRequest,
    UpdateUserRoleRequest,
    UpdateUserStatusRequest,
    UserStatsResponse,
)
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
        last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
    )


async def _get_user_or_404(db: AsyncSession, user_id: uuid_mod.UUID) -> User:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "No user with that id"}},
        )
    return user


async def _count_active_admins(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == Role.admin, User.is_active.is_(True))
    )
    return result.scalar_one()


def _escape_like(term: str) -> str:
    """Escape LIKE metacharacters so % and _ in a search term match literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/users", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, description="Filter by first/last name or email (case-insensitive)"),
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List all users. Requires admin role. Optional case-insensitive search across
    first name, last name, and email."""
    offset = (page - 1) * page_size

    filters = []
    if search:
        pattern = f"%{_escape_like(search)}%"
        filters.append(
            or_(
                User.first_name.ilike(pattern, escape="\\"),
                User.last_name.ilike(pattern, escape="\\"),
                User.email_address.ilike(pattern, escape="\\"),
            )
        )

    total_result = await db.execute(select(func.count()).select_from(User).where(*filters))
    total = total_result.scalar_one()

    result = await db.execute(
        select(User)
        .where(*filters)
        .offset(offset)
        .limit(page_size)
        .order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    return PaginatedResponse(
        items=[_to_item(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/users/stats", response_model=UserStatsResponse)
async def user_stats(
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Role/verification/status counts across ALL users, for the admin summary cards.
    Independent of the list endpoint's pagination and search (Story 8.1)."""

    async def count(*criteria) -> int:
        result = await db.execute(select(func.count()).select_from(User).where(*criteria))
        return result.scalar_one()

    return UserStatsResponse(
        total=await count(),
        learners=await count(User.role == Role.learner),
        course_designers=await count(User.role == Role.course_designer),
        admins=await count(User.role == Role.admin),
        verified=await count(User.email_verified.is_(True)),
        active=await count(User.is_active.is_(True)),
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


@router.post("/users/create", response_model=AdminUserItem, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Create a user with a chosen role and a password set directly by the admin. The
    account is active and email-verified, so it can log in immediately (Story 8.1).
    Admins may create any role, including other admins."""
    existing = await db.execute(select(User).where(User.email_address == body.email_address))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "DUPLICATE_EMAIL", "message": "A user with that email already exists"}},
        )

    user = User(
        email_address=body.email_address,
        password_hash=hash_password(body.password),
        first_name=body.first_name,
        last_name=body.last_name,
        role=Role[body.role],
        is_active=True,
        email_verified=True,  # admin-created accounts are trusted
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return _to_item(user)


@router.patch("/users/{user_id}/role", response_model=AdminUserItem)
async def update_user_role(
    user_id: uuid_mod.UUID,
    body: UpdateUserRoleRequest,
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Change a user's role. Takes effect on the target's NEXT REQUEST — get_current_user
    re-reads the role from the DB per request; access tokens are not force-revoked.

    Lockout protection (Story 8.1): an admin cannot change their own role, and the last
    remaining active admin cannot be demoted. The self-guard alone is sufficient to keep
    at least one admin (the only path to zero admins is demoting yourself); the last-admin
    check is defense-in-depth."""
    new_role = Role[body.role]
    if user_id == current_user.id and new_role != Role.admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "SELF_ROLE_CHANGE", "message": "You cannot change your own role"}},
        )
    user = await _get_user_or_404(db, user_id)
    if user.role == Role.admin and new_role != Role.admin and await _count_active_admins(db) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "LAST_ADMIN", "message": "Cannot demote the last active admin"}},
        )
    user.role = new_role
    await db.commit()
    await db.refresh(user)
    return _to_item(user)


@router.patch("/users/{user_id}/status", response_model=AdminUserItem)
async def update_user_status(
    user_id: uuid_mod.UUID,
    body: UpdateUserStatusRequest,
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Activate or deactivate a user. Deactivated users can no longer authenticate
    (enforced per-request by get_current_user and by login). An admin cannot deactivate
    their own account, nor the last active admin. Story 8.1."""
    if user_id == current_user.id and not body.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "SELF_DEACTIVATION",
                    "message": "You cannot deactivate your own account",
                }
            },
        )
    user = await _get_user_or_404(db, user_id)
    if (
        not body.is_active
        and user.is_active
        and user.role == Role.admin
        and await _count_active_admins(db) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "LAST_ADMIN", "message": "Cannot deactivate the last active admin"}},
        )
    user.is_active = body.is_active
    await db.commit()
    await db.refresh(user)
    return _to_item(user)
