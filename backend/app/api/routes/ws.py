"""WebSocket endpoint for the learner affect-detection loop.

This is the transport substrate for Epic 4 (affect detection + agent loop) and Epic 5
(adaptation delivery). It establishes the persistent socket, validates the JWT on
handshake, restores per-session state, drives heartbeats, and emits research events.

Architecture references:
  - architecture.md lines 310-328  (protocol, single connection per learner, multiplexed)
  - architecture.md line 489       (snake_case both directions — exception to REST camelCase)
  - architecture.md lines 631-647  (error handling, malformed-message rules)
  - architecture.md lines 651-653  (auth: JWT in query param, validated once on handshake)

Close codes (custom, RFC 6455 4000-4999 range):
  - 4001  superseded_by_new_connection  (second tab supersedes first)
  - 4401  authentication_failed         (missing/invalid/expired token, wrong role)
"""

import json
import time
import uuid as uuid_mod
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import decode_token
from app.models.user import Role, User
from app.services.connection_manager import (
    WS_CLOSE_AUTH_FAILED,
    connection_manager,
)
from app.services.research_logger import emit as emit_research_event

logger = structlog.get_logger(__name__)

router = APIRouter()

_MAX_RAW_LOG_LEN = 200  # truncate inbound payload in warning logs


def _now_ms() -> int:
    return int(time.time() * 1000)


def _system_message(action: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a `{type: "system", action: ..., ts, data}` server message."""
    return {"type": "system", "action": action, "ts": _now_ms(), "data": data or {}}


async def _safe_emit(event: dict[str, Any]) -> None:
    """Emit a research event without ever propagating exceptions to the caller."""
    try:
        await emit_research_event(event)
    except Exception:
        logger.exception("research_event_emit_swallowed", event_type=event.get("event_type"))


async def _resolve_learner(token: str, db: AsyncSession) -> tuple[User | None, str]:
    """Decode JWT and load the learner. Returns (user, error_reason).

    `error_reason` is one of: "missing_token", "invalid_token", "expired_token",
    "role_not_authorized", or "" on success. User is None on failure.
    """
    if not token:
        return None, "missing_token"

    try:
        payload = decode_token(token)
    except JWTError as exc:
        reason = "expired_token" if "expired" in str(exc).lower() else "invalid_token"
        return None, reason

    if payload.get("type") != "access":
        return None, "invalid_token"

    sub = payload.get("sub")
    if not sub:
        return None, "invalid_token"

    try:
        uid = uuid_mod.UUID(sub)
    except (ValueError, AttributeError):
        return None, "invalid_token"

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        return None, "invalid_token"
    if user.role != Role.learner:
        return None, "role_not_authorized"

    return user, ""


async def _load_session_state(user_id: str) -> dict[str, Any] | None:
    """Look up session state for restoration on reconnect.

    Story 4.1 stubs this: returns None for everyone. Story 4.4+ populates the real
    `session:learner:{user_id}` Redis key with the agent loop's current state.
    """
    # NOTE Story 4.5+ will replace with redis_service.get_json("session:learner:{user_id}").
    return None


def _handle_heartbeat(envelope: dict[str, Any]) -> dict[str, Any]:
    """Build `heartbeat_ack` from an inbound heartbeat envelope."""
    inbound_seq = (envelope.get("data") or {}).get("seq")
    return {
        "type": "heartbeat_ack",
        "ts": _now_ms(),
        "data": {"seq": inbound_seq, "server_ts": _now_ms()},
    }


@router.websocket("")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Single multiplexed WebSocket per learner. Auth on handshake; message loop until disconnect."""

    user, reason = await _resolve_learner(token, db)
    if user is None:
        await websocket.close(code=WS_CLOSE_AUTH_FAILED, reason=reason)
        return

    await websocket.accept()
    user_id = str(user.id)
    session_id = uuid_mod.uuid4().hex
    accept_ms = _now_ms()

    superseded = await connection_manager.connect(user_id, websocket)

    # Send connected or session_restored
    prior_state = await _load_session_state(user_id)
    if prior_state is not None:
        await websocket.send_json(_system_message("session_restored", prior_state))
        await _safe_emit({
            "event_type": "ws_session_restored",
            "learner_id": user_id,
            "session_id": session_id,
            "cycle_number": 0,
            "timestamp": _now_ms(),
            "payload": {"keys": list(prior_state.keys())},
        })
    else:
        await websocket.send_json(_system_message("connected", {"welcome": True}))

    await _safe_emit({
        "event_type": "ws_reconnected" if superseded else "ws_connected",
        "learner_id": user_id,
        "session_id": session_id,
        "cycle_number": 0,
        "timestamp": accept_ms,
        "payload": {"superseded_prior": superseded},
    })

    close_reason = "normal"
    try:
        while True:
            raw = await websocket.receive_text()

            try:
                envelope = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(
                    "ws_invalid_message",
                    user_id=user_id,
                    raw=raw[:_MAX_RAW_LOG_LEN],
                    reason="json_decode_error",
                )
                continue

            if not isinstance(envelope, dict) or "type" not in envelope or "ts" not in envelope:
                logger.warning(
                    "ws_invalid_message",
                    user_id=user_id,
                    raw=raw[:_MAX_RAW_LOG_LEN],
                    reason="missing_required_fields",
                )
                continue

            msg_type = envelope.get("type")

            if msg_type == "heartbeat":
                await websocket.send_json(_handle_heartbeat(envelope))
                continue

            if msg_type == "client_hello":
                # Reserved for future use; ack via a system.connected refresh is not required.
                continue

            # Unknown but well-formed types: log + drop (forward-compat).
            logger.warning(
                "ws_invalid_message",
                user_id=user_id,
                raw=raw[:_MAX_RAW_LOG_LEN],
                reason="unknown_type",
            )

    except WebSocketDisconnect as disc:
        close_reason = f"client_disconnect:{disc.code}"
    except Exception:
        logger.exception("ws_handler_unexpected_error", user_id=user_id)
        close_reason = "server_error"
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        connection_manager.disconnect(user_id, websocket)
        await _safe_emit({
            "event_type": "ws_disconnected",
            "learner_id": user_id,
            "session_id": session_id,
            "cycle_number": 0,
            "timestamp": _now_ms(),
            "payload": {
                "reason": close_reason,
                "duration_ms": _now_ms() - accept_ms,
            },
        })
