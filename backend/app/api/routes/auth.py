"""Auth API endpoints: register, login, refresh, me, email verification, password reset."""

import uuid as uuid_mod
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, get_db, require_role
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_url_token,
    hash_password,
    hash_url_token,
    verify_password,
)
from app.models.email_token import EMAIL_VERIFICATION, PASSWORD_RESET, EmailToken
from app.models.user import Role, User
from app.schemas.base import camelise_keys
from app.schemas.auth import (
    ChangePasswordRequest,
    ConsentRequest,
    DeleteAccountRequest,
    ErasureReceipt,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
    WebcamModeRequest,
)
from app.services import data_rights_service
from app.services.email_service import (
    send_password_changed_email,
    send_password_reset_email,
    send_verification_email,
    send_welcome_email,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _add_email_token(db: AsyncSession, user: User, purpose: str, expires_at: datetime) -> str:
    """Create an EmailToken row (storing only the hash) and return the plaintext token."""
    raw = generate_url_token()
    db.add(
        EmailToken(
            user_id=user.id,
            token_hash=hash_url_token(raw),
            purpose=purpose,
            expires_at=expires_at,
        )
    )
    return raw


def _is_expired(dt: datetime) -> bool:
    # SQLite returns naive datetimes for timezone=True columns — normalize to UTC.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt < datetime.now(timezone.utc)


def _build_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email_address=user.email_address,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role.value,
        age_range=user.age_range,
        degree_program=user.degree_program,
        consent_given_at=user.consent_given_at.isoformat() if user.consent_given_at else None,
        webcam_enabled=user.webcam_enabled or False,
    )


def _resolve_role(invite_code: str | None) -> Role:
    """Map an optional designer invite code to a role. Absent → learner. Present → must
    match the configured DESIGNER_INVITE_CODE, else INVALID_INVITE_CODE."""
    if not invite_code:
        return Role.learner
    if not settings.DESIGNER_INVITE_CODE or invite_code != settings.DESIGNER_INVITE_CODE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_INVITE_CODE", "message": "Invalid designer invite code"}},
        )
    return Role.course_designer


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check for duplicate email
    result = await db.execute(select(User).where(User.email_address == body.email_address))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "DUPLICATE_EMAIL", "message": "Already have an account? Sign in"}},
        )

    role = _resolve_role(body.designer_invite_code)

    user = User(
        email_address=body.email_address,
        password_hash=hash_password(body.password),
        first_name=body.first_name,
        last_name=body.last_name,
        age_range=body.age_range,
        degree_program=body.degree_program,
        role=role,
        is_active=True,
        email_verified=False,
    )
    db.add(user)
    await db.flush()  # populate user.id for the token FK

    expires = datetime.now(timezone.utc) + timedelta(
        hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS
    )
    raw_token = _add_email_token(db, user, EMAIL_VERIFICATION, expires)
    await db.commit()

    link = f"{settings.FRONTEND_BASE_URL}/verify-email?token={raw_token}"
    await send_verification_email(user.email_address, link)

    # No tokens issued — login is gated on verification.
    return MessageResponse(
        message="Account created. Check your email for a verification link to activate your account.",
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email_address == body.email_address))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password"}},
        )

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "EMAIL_NOT_VERIFIED",
                    "message": "Please verify your email before signing in.",
                }
            },
        )

    return _token_response(user)


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
    new_refresh_token = create_refresh_token(str(user.id))

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return _build_user_response(current_user)


@router.get("/dev-credentials")
async def dev_credentials():
    """Return the seeded role-based accounts for the login page in dev mode.

    Returns 404 unless BOTH conditions hold: the environment is not production, and
    `EXPOSE_DEV_CREDENTIALS` is set. The route is unauthenticated and its body is the plaintext
    password of the seeded ADMIN account, so a single mis-copied environment file was the whole
    distance between a normal deployment and handing out admin credentials to anyone who knew the
    path. One flag is not enough separation for that payload; the environment check cannot be
    switched on by accident when copying a working `.env` from a developer machine.
    """
    if settings.ENVIRONMENT.lower() == "production" or not settings.EXPOSE_DEV_CREDENTIALS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Not found"}},
        )
    from app.db.seed import get_dev_credentials

    return {
        "environment": settings.ENVIRONMENT,
        "accounts": get_dev_credentials(),
    }


@router.post("/consent", response_model=UserResponse)
async def give_consent(
    body: ConsentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    """Record informed consent for the learner (idempotent — never overwrites once set)."""
    if current_user.consent_given_at is None:
        current_user.consent_given_at = func.now()
        await db.commit()
        await db.refresh(current_user)
    return _build_user_response(current_user)


@router.post("/webcam-mode", response_model=UserResponse)
async def set_webcam_mode(
    body: WebcamModeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    """Set the learner's webcam mode preference."""
    current_user.webcam_enabled = body.webcam_enabled
    await db.commit()
    await db.refresh(current_user)
    return _build_user_response(current_user)


# --- Email verification + password reset ---

_GENERIC_EMAIL_SENT = MessageResponse(
    message="If an account matches that email, we've sent a message with next steps.",
)


@router.post("/verify-email", response_model=TokenResponse)
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    """Confirm an email-verification token, mark the user verified, and auto-login."""
    result = await db.execute(
        select(EmailToken).where(
            EmailToken.token_hash == hash_url_token(body.token),
            EmailToken.purpose == EMAIL_VERIFICATION,
        )
    )
    token = result.scalar_one_or_none()
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid verification link"}},
        )
    if token.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "TOKEN_USED", "message": "This link has already been used"}},
        )
    if _is_expired(token.expires_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "TOKEN_EXPIRED", "message": "This verification link has expired"}},
        )

    user = (await db.execute(select(User).where(User.id == token.user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid verification link"}},
        )

    user.email_verified = True
    token.used_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    # Welcome learners once their email is confirmed (best-effort; never blocks login).
    if user.role == Role.learner:
        await send_welcome_email(user.email_address, user.first_name)

    return _token_response(user)


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(body: ResendVerificationRequest, db: AsyncSession = Depends(get_db)):
    """Issue a fresh verification email. Always returns a generic message (no enumeration)."""
    user = (
        await db.execute(select(User).where(User.email_address == body.email_address))
    ).scalar_one_or_none()

    if user is not None and not user.email_verified:
        expires = datetime.now(timezone.utc) + timedelta(
            hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS
        )
        raw_token = _add_email_token(db, user, EMAIL_VERIFICATION, expires)
        await db.commit()
        link = f"{settings.FRONTEND_BASE_URL}/verify-email?token={raw_token}"
        await send_verification_email(user.email_address, link)

    return _GENERIC_EMAIL_SENT


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Email a password-reset link. Always returns a generic message (no enumeration)."""
    user = (
        await db.execute(select(User).where(User.email_address == body.email_address))
    ).scalar_one_or_none()

    if user is not None and user.is_active:
        expires = datetime.now(timezone.utc) + timedelta(
            minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
        )
        raw_token = _add_email_token(db, user, PASSWORD_RESET, expires)
        await db.commit()
        link = f"{settings.FRONTEND_BASE_URL}/reset-password?token={raw_token}"
        await send_password_reset_email(user.email_address, link)

    return _GENERIC_EMAIL_SENT


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Validate a reset token, set the new password, and invalidate outstanding reset tokens."""
    result = await db.execute(
        select(EmailToken).where(
            EmailToken.token_hash == hash_url_token(body.token),
            EmailToken.purpose == PASSWORD_RESET,
        )
    )
    token = result.scalar_one_or_none()
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid reset link"}},
        )
    if token.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "TOKEN_USED", "message": "This link has already been used"}},
        )
    if _is_expired(token.expires_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "TOKEN_EXPIRED", "message": "This reset link has expired"}},
        )

    user = (await db.execute(select(User).where(User.id == token.user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid reset link"}},
        )

    user.password_hash = hash_password(body.password)
    # Invalidate every outstanding reset token for this user (including the one just used).
    await db.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user.id,
            EmailToken.purpose == PASSWORD_RESET,
            EmailToken.used_at.is_(None),
        )
        .values(used_at=datetime.now(timezone.utc))
    )
    await db.commit()

    # Security confirmation (best-effort; never blocks the reset).
    await send_password_changed_email(user.email_address)

    return MessageResponse(message="Your password has been reset. You can now sign in.")


# ---------------------------------------------------------------------------
# Data rights (Story: pilot readiness)
#
# The consent form and the privacy policy both commit to deletion on request and to letting a
# participant see what is held about them. Until these endpoints existed, both commitments were
# honoured by hand — workable for one researcher, not a control, and not something a participant
# can exercise without asking a person for a favour.
# ---------------------------------------------------------------------------


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change the signed-in account's password.

    Requires the current password even though the caller holds a valid token: a token left behind
    on a shared machine should not be enough to lock the real owner out of their own account.
    """
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_CREDENTIALS",
                              "message": "Current password is incorrect"}},
        )

    current_user.password_hash = hash_password(body.new_password)
    # Any outstanding reset tokens are spent: a live reset link is a second door into an account
    # whose owner has just deliberately changed the lock.
    await db.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == current_user.id,
            EmailToken.purpose == PASSWORD_RESET,
            EmailToken.used_at.is_(None),
        )
        .values(used_at=func.now())
    )
    await db.commit()

    try:
        await send_password_changed_email(current_user.email_address)
    except Exception:  # noqa: BLE001 — the password IS changed; a mail failure must not undo it
        logger.warning("password_changed_email_failed", user_id=str(current_user.id))

    return MessageResponse(message="Password changed")


@router.get("/me/export")
async def export_my_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Everything held about the signed-in account, as JSON.

    Deliberately exhaustive rather than curated — including the interaction telemetry and the
    research event log. A subject-access response that quietly omitted those would be answering
    an easier question than the one being asked.
    """
    # `camelise_keys` rather than a response model: the export has no fixed schema — it is a dump
    # of whatever tables hold rows for this learner — so there is nothing for `CamelModel` to
    # declare, and returning snake_case here alone would break the wire convention.
    return camelise_keys(await data_rights_service.export_learner(db, current_user.id))


@router.post("/me/delete", response_model=ErasureReceipt)
async def delete_my_account(
    body: DeleteAccountRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Erase this account and everything recorded about it. Irreversible.

    Returns a per-table receipt rather than a bare 204, so a participant who exercises the right
    gets something they can keep: "deleted" with no numbers is indistinguishable from a no-op.

    Note that `research_events` has no foreign key to `users` and is therefore NOT removed by the
    database cascade — `data_rights_service` deletes it explicitly. Relying on the cascade alone
    would report success while leaving every affect reading for that participant in place.
    """
    if not verify_password(body.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_CREDENTIALS", "message": "Password is incorrect"}},
        )
    if body.confirm != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "CONFIRMATION_REQUIRED",
                              "message": 'Send confirm: "DELETE" to erase this account'}},
        )

    counts = await data_rights_service.erase_learner(db, current_user.id)
    # The counts are a `dict[str, int]`, so `CamelModel` camelises the FIELD (`deleted`) but not
    # the table names inside it.
    return ErasureReceipt(deleted=camelise_keys(counts))
