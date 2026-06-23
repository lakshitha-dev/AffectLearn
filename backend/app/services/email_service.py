"""Transactional email via Azure Communication Services (ACS) Email.

All categories — verification, password reset, welcome, password-changed — render from a
single branded, table-based HTML template (``_render``) with inline CSS so they survive
Gmail/Outlook, plus a plain-text alternative. The ACS SDK is synchronous, so sends run in
a worker thread (``asyncio.to_thread``) to avoid blocking the event loop.

Degradation: when ``EMAIL_ENABLED`` is False or no connection string is configured, the
content is logged via structlog instead of sent. Send failures are logged and swallowed —
account flows must never fail because of email infrastructure (users can always retry).
"""

import asyncio
from datetime import datetime, timezone

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

_APP_NAME = "AffectLearn"
_TAGLINE = "Adaptive learning that responds to how you feel."

# Brand palette (mirrors the landing CSS).
_BRAND = "#2563eb"
_GREEN = "#16a34a"
_AMBER = "#d97706"
_INK = "#0f172a"
_TEXT = "#334155"
_MUTED = "#64748b"
_FAINT = "#94a3b8"
_BORDER = "#e2e8f0"
_BG = "#f1f5f9"

_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif"


def _is_configured() -> bool:
    return settings.EMAIL_ENABLED and bool(settings.ACS_CONNECTION_STRING)


def _render(
    *,
    to: str,
    preheader: str,
    heading: str,
    intro: str,
    outro: str,
    accent: str,
    cta_label: str | None = None,
    cta_url: str | None = None,
) -> tuple[str, str]:
    """Build (html, plain_text) for one branded email."""
    year = datetime.now(timezone.utc).year

    cta_html = ""
    if cta_label and cta_url:
        cta_html = f"""
        <tr><td style="padding:8px 40px 4px;">
          <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
            <td align="center" style="border-radius:8px;background:{accent};">
              <a href="{cta_url}" style="display:inline-block;padding:13px 28px;font-family:{_FONT};font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:8px;">{cta_label}</a>
            </td>
          </tr></table>
          <p style="margin:16px 0 0;font-size:13px;line-height:1.5;color:{_MUTED};font-family:{_FONT};">Or paste this link into your browser:<br>
            <a href="{cta_url}" style="color:{accent};word-break:break-all;">{cta_url}</a></p>
        </td></tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="x-apple-disable-message-reformatting">
<title>{heading}</title>
</head>
<body style="margin:0;padding:0;background:{_BG};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_BG};">
<tr><td align="center" style="padding:32px 16px;">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background:#ffffff;border:1px solid {_BORDER};border-radius:12px;overflow:hidden;">
    <tr><td style="height:4px;background:{accent};font-size:0;line-height:0;">&nbsp;</td></tr>
    <tr><td align="center" style="padding:28px 40px 4px;font-family:{_FONT};">
      <span style="font-size:22px;font-weight:600;color:{accent};letter-spacing:-0.02em;">Affect<span style="font-weight:800;">Learn</span></span>
    </td></tr>
    <tr><td style="padding:16px 40px 0;font-family:{_FONT};">
      <h1 style="margin:0 0 14px;font-size:22px;line-height:1.3;color:{_INK};">{heading}</h1>
      <p style="margin:0 0 8px;font-size:15px;line-height:1.6;color:{_TEXT};">{intro}</p>
    </td></tr>
    {cta_html}
    <tr><td style="padding:12px 40px 24px;font-family:{_FONT};">
      <p style="margin:0;font-size:14px;line-height:1.6;color:{_MUTED};">{outro}</p>
    </td></tr>
    <tr><td style="padding:0 40px;"><div style="height:1px;background:{_BORDER};font-size:0;line-height:0;">&nbsp;</div></td></tr>
    <tr><td style="padding:20px 40px 26px;font-family:{_FONT};">
      <p style="margin:0 0 6px;font-size:12px;line-height:1.5;color:{_FAINT};">{_APP_NAME} — {_TAGLINE}</p>
      <p style="margin:0;font-size:12px;line-height:1.5;color:{_FAINT};">This is an automated message, please don&#39;t reply. You received it because this action was requested for {to}.</p>
    </td></tr>
  </table>
  <p style="margin:16px 0 0;font-size:11px;color:{_FAINT};font-family:{_FONT};">© {year} {_APP_NAME} · <a href="{settings.FRONTEND_BASE_URL}" style="color:{_FAINT};">affectlearn.tech</a></p>
</td></tr>
</table>
</body>
</html>"""

    plain_cta = f"\n{cta_label}:\n{cta_url}\n" if cta_label and cta_url else ""
    plain = (
        f"{heading}\n\n"
        f"{intro}\n"
        f"{plain_cta}\n"
        f"{outro}\n\n"
        f"—\n{_APP_NAME} — {_TAGLINE}\n"
        f"This is an automated message, please don't reply.\n"
        f"© {year} {_APP_NAME} · affectlearn.tech"
    )
    return html, plain


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


async def _send(to: str, subject: str, html: str, plain: str, *, kind: str) -> None:
    if not _is_configured():
        logger.info(
            "email_disabled_not_sent",
            kind=kind,
            to=to,
            subject=subject,
            hint="Set EMAIL_ENABLED=true and ACS_CONNECTION_STRING to send real emails.",
        )
        return
    try:
        await asyncio.to_thread(_send_sync, to, subject, html, plain)
        logger.info("email_sent", kind=kind, to=to)
    except Exception as exc:  # noqa: BLE001 — never let email break the request
        logger.error("email_send_failed", kind=kind, to=to, error=str(exc))


async def send_verification_email(to: str, link: str) -> None:
    hours = settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS
    html, plain = _render(
        to=to,
        preheader=f"Confirm your email to activate your {_APP_NAME} account.",
        heading="Verify your email",
        intro=(
            f"Welcome to {_APP_NAME}! Confirm your email address to activate your "
            "account and start learning."
        ),
        outro=(
            f"This link expires in {hours} hours. If you didn't create an account, "
            "you can safely ignore this email."
        ),
        accent=_BRAND,
        cta_label="Verify my email",
        cta_url=link,
    )
    await _send(to, f"Verify your {_APP_NAME} email", html, plain, kind="verification")


async def send_password_reset_email(to: str, link: str) -> None:
    minutes = settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    html, plain = _render(
        to=to,
        preheader=f"Choose a new password for your {_APP_NAME} account.",
        heading="Reset your password",
        intro=(
            f"We received a request to reset the password for your {_APP_NAME} account. "
            "Choose a new one below."
        ),
        outro=(
            f"This link expires in {minutes} minutes. If you didn't request this, you can "
            "safely ignore this email — your password won't change."
        ),
        accent=_BRAND,
        cta_label="Reset password",
        cta_url=link,
    )
    await _send(to, f"Reset your {_APP_NAME} password", html, plain, kind="password_reset")


async def send_welcome_email(to: str, first_name: str) -> None:
    name = first_name.strip() or "there"
    html, plain = _render(
        to=to,
        preheader=f"Your {_APP_NAME} account is verified — start learning.",
        heading=f"You're all set, {name}!",
        intro=(
            f"Your email is verified and your {_APP_NAME} account is ready. Jump into a "
            "course — the platform adapts in real time to how you learn."
        ),
        outro=(
            "Have a webcam? Optional focus detection helps the platform adapt better — "
            "you're always in control, and no video is ever stored."
        ),
        accent=_GREEN,
        cta_label="Start learning",
        cta_url=f"{settings.FRONTEND_BASE_URL}/courses",
    )
    await _send(to, f"Welcome to {_APP_NAME}", html, plain, kind="welcome")


async def send_password_changed_email(to: str) -> None:
    html, plain = _render(
        to=to,
        preheader=f"Your {_APP_NAME} password was just changed.",
        heading="Your password was changed",
        intro=(
            f"This is a confirmation that the password for your {_APP_NAME} account was "
            "just changed."
        ),
        outro=(
            "If you made this change, no action is needed. If you didn't, reset your "
            "password immediately using the button above and secure your account."
        ),
        accent=_AMBER,
        cta_label="Reset your password",
        cta_url=f"{settings.FRONTEND_BASE_URL}/forgot-password",
    )
    await _send(to, f"Your {_APP_NAME} password was changed", html, plain, kind="password_changed")
