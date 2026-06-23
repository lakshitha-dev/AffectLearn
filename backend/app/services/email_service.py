"""Transactional email via Azure Communication Services (ACS) Email.

Sends the two account emails — verification and password reset. The ACS SDK is
synchronous, so sends run in a worker thread (``asyncio.to_thread``) to avoid blocking
the event loop.

Degradation: when ``EMAIL_ENABLED`` is False or no connection string is configured, the
link is logged via structlog instead of sent. Send failures are logged and swallowed —
account creation/reset requests must never fail because of email infrastructure (the
user can always trigger a resend).
"""

import asyncio

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

_APP_NAME = "AffectLearn"


def _is_configured() -> bool:
    return settings.EMAIL_ENABLED and bool(settings.ACS_CONNECTION_STRING)


def _send_sync(to: str, subject: str, html: str, plain: str) -> None:
    """Blocking ACS send — run via asyncio.to_thread. Imported lazily so the dependency
    is only required when email is actually enabled."""
    from azure.communication.email import EmailClient

    client = EmailClient.from_connection_string(settings.ACS_CONNECTION_STRING)
    message = {
        "senderAddress": settings.ACS_SENDER_ADDRESS,
        "recipients": {"to": [{"address": to}]},
        "content": {"subject": subject, "plainText": plain, "html": html},
    }
    poller = client.begin_send(message)
    poller.result()  # block until the send operation completes


async def _send(to: str, subject: str, html: str, plain: str, *, link: str, kind: str) -> None:
    if not _is_configured():
        logger.info(
            "email_disabled_link_logged",
            kind=kind,
            to=to,
            link=link,
            hint="Set EMAIL_ENABLED=true and ACS_CONNECTION_STRING to send real emails.",
        )
        return
    try:
        await asyncio.to_thread(_send_sync, to, subject, html, plain)
        logger.info("email_sent", kind=kind, to=to)
    except Exception as exc:  # noqa: BLE001 — never let email break the request
        logger.error("email_send_failed", kind=kind, to=to, error=str(exc))


async def send_verification_email(to: str, link: str) -> None:
    subject = f"Verify your {_APP_NAME} email"
    plain = (
        f"Welcome to {_APP_NAME}!\n\n"
        f"Confirm your email address to activate your account:\n{link}\n\n"
        f"This link expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours. "
        "If you didn't create an account, you can ignore this email."
    )
    html = (
        f"<p>Welcome to <strong>{_APP_NAME}</strong>!</p>"
        f"<p>Confirm your email address to activate your account:</p>"
        f'<p><a href="{link}">Verify my email</a></p>'
        f"<p>This link expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours. "
        "If you didn't create an account, you can ignore this email.</p>"
    )
    await _send(to, subject, html, plain, link=link, kind="verification")


async def send_password_reset_email(to: str, link: str) -> None:
    subject = f"Reset your {_APP_NAME} password"
    plain = (
        f"We received a request to reset your {_APP_NAME} password.\n\n"
        f"Choose a new password here:\n{link}\n\n"
        f"This link expires in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes. "
        "If you didn't request this, you can safely ignore this email."
    )
    html = (
        f"<p>We received a request to reset your <strong>{_APP_NAME}</strong> password.</p>"
        f'<p><a href="{link}">Choose a new password</a></p>'
        f"<p>This link expires in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes. "
        "If you didn't request this, you can safely ignore this email.</p>"
    )
    await _send(to, subject, html, plain, link=link, kind="password_reset")
