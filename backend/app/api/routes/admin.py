"""Admin API endpoints."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

import structlog

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db, require_role
from app.core.security import generate_url_token, hash_password, hash_url_token
from app.models.email_token import PASSWORD_RESET, EmailToken
from app.models.user import Role, User
from app.schemas.auth import AdminUserItem, AdminUserUpdate, CreateDesignerRequest, ErasureReceipt
from app.schemas.base import PaginatedResponse, camelise_keys
from app.services import data_rights_service
from app.services.email_service import send_designer_invite_email

logger = structlog.get_logger(__name__)

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
    search: str | None = Query(None, min_length=1, max_length=200),
    role: Literal["learner", "course_designer", "admin"] | None = Query(None),
    is_active: bool | None = Query(None),
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """List users, filterable by name, email, role and status (Story 8.1).

    Filtering happens in SQL rather than in the client. The admin console previously fetched a
    single hardcoded page of 100 and searched it in the browser, which silently stops working at
    the 101st account — the pilot's own recruitment target is inside that margin.
    """
    conditions = []
    if search:
        term = f"%{search.lower()}%"
        conditions.append(
            or_(
                func.lower(User.email_address).like(term),
                func.lower(User.first_name).like(term),
                func.lower(User.last_name).like(term),
            )
        )
    if role is not None:
        conditions.append(User.role == Role(role))
    if is_active is not None:
        conditions.append(User.is_active.is_(is_active))

    base = select(User)
    count_stmt = select(func.count()).select_from(User)
    for condition in conditions:
        base = base.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(
        base.order_by(User.created_at.desc()).offset(offset).limit(page_size)
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


# ---------------------------------------------------------------------------
# Managing an existing account
# ---------------------------------------------------------------------------
#
# `/admin/users` could list and invite and nothing else: no role change, no way to deactivate a
# leaver, no way to reverse a mistaken invite. Story 8.1 asks for exactly this, and the
# enforcement was already free — `get_current_user` rejects `is_active=False` on every request,
# so deactivating takes effect on the account's next call with no extra plumbing.


def _refuse_self_administration(current_user: User, target: User, what: str) -> None:
    """An admin may not demote or deactivate themselves.

    Not paternalism: this is the only role that can grant the role back. A sole administrator who
    clicks the wrong row locks the deployment out of its own administration, and the repair is a
    manual database edit — which during a pilot means an outage of the controls that start and
    stop the study.
    """
    if current_user.id == target.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "CANNOT_SELF_ADMINISTER",
                    "message": f"You cannot {what} your own account",
                }
            },
        )


async def _get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "User not found"}},
        )
    return user


@router.patch("/users/{user_id}", response_model=AdminUserItem)
async def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Change a user's role or active status."""
    target = await _get_user_or_404(db, user_id)
    changes = body.model_dump(exclude_unset=True)

    if "role" in changes and changes["role"] != target.role.value:
        _refuse_self_administration(current_user, target, "change the role of")
        target.role = Role(changes["role"])

    if "is_active" in changes and changes["is_active"] != target.is_active:
        if not changes["is_active"]:
            _refuse_self_administration(current_user, target, "deactivate")
        target.is_active = bool(changes["is_active"])

    await db.commit()
    await db.refresh(target)
    return _to_item(target)


@router.post("/users/{user_id}/withdraw", response_model=ErasureReceipt)
async def withdraw_participant(
    user_id: uuid.UUID,
    current_user: User = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
):
    """Withdraw a participant and erase everything recorded about them (Story 8.7 / FR49).

    Delegates to the same `data_rights_service.erase_learner` the learner's own delete button
    uses, so a coordinator-initiated withdrawal and a self-service one remove exactly the same
    rows — one erasure path, one thing to get right, one thing to audit.

    Returns the per-table receipt rather than a bare 204: "the data is gone" is a claim a study
    has to be able to evidence, and a count of what was removed is that evidence.

    Deliberately refuses to erase an ADMIN account, including your own. Withdrawal is a
    participant action; an administrator leaving is an account change, not a research erasure.
    """
    target = await _get_user_or_404(db, user_id)
    if target.role == Role.admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "CANNOT_WITHDRAW_ADMIN",
                    "message": "Administrator accounts are not study participants",
                }
            },
        )

    counts = await data_rights_service.erase_learner(db, target.id)
    logger.info(
        "participant_withdrawn",
        withdrawn_user_id=str(user_id),
        by_admin_id=str(current_user.id),
        counts=counts,
    )
    # Same shape as the learner's own erasure receipt (`POST /auth/me/delete`): `CamelModel`
    # camelises the FIELD, and the table names inside the dict are camelised explicitly. One
    # erasure path deserves one response shape.
    return ErasureReceipt(deleted=camelise_keys(counts))
