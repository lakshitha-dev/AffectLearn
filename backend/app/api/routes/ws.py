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
from jose.exceptions import ExpiredSignatureError
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
from app.services import fusion_buffer
from app.agents.fusion import forced_mode, fuse_modalities
from app.agents.graph import get_graph
from app.agents.state import make_initial_state

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
    except ExpiredSignatureError:
        return None, "expired_token"
    except JWTError:
        return None, "invalid_token"

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


async def _handle_facial_features(
    envelope: dict[str, Any], user_id: str, session_id: str, db: AsyncSession | None = None
) -> None:
    """Drive the LangGraph cycle for one `facial_features` message and emit an event.

    Builds an `AgentState`, invokes the compiled graph (affect detection runs the
    CNN-LSTM and writes the affect CATEGORY), and emits a `facial_affect_detected`
    research event. Errors in the affect path are logged + mapped to an error marker,
    never thrown (architecture lines 632/647) — a bad cycle must not break the
    WebSocket. An empty cycle (no face detected the whole window) is recorded so
    downstream can fall back to behavioural-only weighting.
    """
    data = envelope.get("data") or {}
    cycle = int(data.get("cycle_number", 0) or 0)
    frames_captured = int(data.get("frames_captured", 0) or 0)
    dropped = int(data.get("dropped_frames", 0) or 0)

    result_state = None
    error = None
    try:
        initial_state = make_initial_state(
            learner_id=user_id,
            session_id=session_id,
            cycle_number=cycle,
            facial_payload=data,
            db=db,
        )
        result_state = await get_graph().ainvoke(initial_state)
    except FileNotFoundError as exc:
        error = "model_unavailable"
        logger.warning("affect_model_unavailable", user_id=user_id, cycle=cycle, detail=str(exc))
    except Exception:
        error = "inference_error"
        logger.exception("affect_inference_failed", user_id=user_id, cycle=cycle)

    payload: dict[str, Any] = {"frames_captured": frames_captured, "dropped_frames": dropped}
    if result_state is not None and result_state.get("affect_state"):
        inference = result_state.get("facial_inference") or {}
        payload.update(
            affect_state=result_state["affect_state"],
            affect_confidence=round(float(result_state.get("affect_confidence", 0.0)), 4),
            detection_mode=result_state.get("detection_mode"),
            affect_source=result_state.get("affect_source"),
            # raw engagement output preserved for research (snake_case on the wire) —
            # incl. the full softmax `probs` so the distribution is recoverable for
            # post-hoc remapping / calibration (AC6, Success Criteria).
            engagement_level=inference.get("engagement_level"),
            label=inference.get("label"),
            confidence=round(float(inference["confidence"]), 4) if "confidence" in inference else None,
            probs=inference.get("probs"),
            frames_used=inference.get("frames_used"),
        )
    elif error:
        payload["error"] = error
    else:
        payload["empty_cycle"] = True  # no face all cycle -> behavioural-only fallback

    payload["forced_mode"] = forced_mode()  # ablation marker on every event (Story 4.4c FR14)
    await _safe_emit({
        "event_type": "facial_affect_detected",
        "learner_id": user_id,
        "session_id": session_id,
        "cycle_number": cycle,
        "timestamp": _now_ms(),
        "payload": payload,
    })

    if result_state is not None and result_state.get("affect_state"):
        await _maybe_fuse("facial", result_state.get("facial_inference") or {},
                          user_id, session_id, cycle)


async def _handle_behavioral_window(
    envelope: dict[str, Any], user_id: str, session_id: str, db: AsyncSession | None = None
) -> None:
    """Drive the LangGraph cycle for one `behavioral_window` message and emit an event.

    Mirrors `_handle_facial_features` but seeds the behavioral payload (Story 4.4b). The
    affect-detection node runs the Bi-LSTM and writes the affect CATEGORY with
    `detection_mode = "behavioral_only"`. Errors degrade to a logged, skipped cycle —
    never thrown (NFR22). An idle window (no events) still classifies the zero-window.

    Privacy (NFR10): raw behavioral events ride only the transient `behavioral_payload`
    and are dropped after the cycle — only counts + results enter the research event.
    """
    data = envelope.get("data") or {}
    cycle = int(data.get("cycle_number", 0) or 0)
    summary = data.get("summary") or {}

    result_state = None
    error = None
    try:
        initial_state = make_initial_state(
            learner_id=user_id,
            session_id=session_id,
            cycle_number=cycle,
            behavioral_payload=data,
            db=db,
        )
        result_state = await get_graph().ainvoke(initial_state)
    except FileNotFoundError as exc:
        error = "behavioral_model_unavailable"
        logger.warning(
            "behavioral_model_unavailable", user_id=user_id, cycle=cycle, detail=str(exc)
        )
    except Exception:
        error = "inference_error"
        logger.exception("behavioral_inference_failed", user_id=user_id, cycle=cycle)

    payload: dict[str, Any] = {
        "event_counts": {
            "mouse_sample_count": summary.get("mouse_sample_count"),
            "mouse_click_count": summary.get("mouse_click_count"),
            "keystroke_count": summary.get("keystroke_count"),
            "scroll_event_count": summary.get("scroll_event_count"),
        },
        "idle": bool(summary.get("idle", False)),
    }
    if result_state is not None and result_state.get("affect_state"):
        inference = result_state.get("behavioral_inference") or {}
        payload.update(
            affect_state=result_state["affect_state"],
            affect_confidence=round(float(result_state.get("affect_confidence", 0.0)), 4),
            detection_mode=result_state.get("detection_mode"),
            affect_source=result_state.get("affect_source"),
            # raw model output preserved for research (ablation analysis in 4.4c / 4.7)
            label=inference.get("label"),
            probs=inference.get("probs"),
            n_bins=inference.get("n_bins"),
        )
    elif error:
        payload["error"] = error
    else:
        payload["empty_cycle"] = True

    payload["forced_mode"] = forced_mode()  # ablation marker on every event (Story 4.4c FR14)
    await _safe_emit({
        "event_type": "behavioral_affect_detected",
        "learner_id": user_id,
        "session_id": session_id,
        "cycle_number": cycle,
        "timestamp": _now_ms(),
        "payload": payload,
    })

    if result_state is not None and result_state.get("affect_state"):
        await _maybe_fuse("behavioral", result_state.get("behavioral_inference") or {},
                          user_id, session_id, cycle)


async def _maybe_fuse(
    modality: str, inference: dict[str, Any], user_id: str, session_id: str, cycle: int
) -> None:
    """Pair this modality's result with a recent counterpart and emit a fused event.

    Late fusion (Story 4.4c): records the unimodal result in the session pairing buffer,
    and if the opposite modality arrived within the window AND ablation mode permits fusion
    (`auto`/`multimodal`), fuses the cached probability vectors and emits a
    `multimodal_affect_detected` research event with fused + per-modality confidences.
    Stores only result dicts (NFR10 — no raw inputs).
    """
    mode = forced_mode()
    if mode not in ("auto", "multimodal"):
        return  # facial_only / behavioral_only: ablation forces unimodal; skip pairing

    # Take the counterpart FIRST. If a pair forms, BOTH slots are consumed (the
    # counterpart is popped here; the current result is never recorded), so a leftover
    # can't re-pair next cycle (M1 — removes the hidden window<cadence dependency).
    # Only record the current result when there's nothing to pair with yet.
    counterpart = fusion_buffer.take_counterpart(session_id, modality, _now_ms())
    if counterpart is None:
        fusion_buffer.record(session_id, modality, inference, _now_ms())
        return

    if modality == "facial":
        fused = fuse_modalities(facial_result=inference, behavioral_result=counterpart)
    else:
        fused = fuse_modalities(facial_result=counterpart, behavioral_result=inference)

    await _safe_emit({
        "event_type": "multimodal_affect_detected",
        "learner_id": user_id,
        "session_id": session_id,
        "cycle_number": cycle,
        "timestamp": _now_ms(),
        "payload": {
            "affect_state": fused["affect_state"],
            "affect_confidence": round(fused["affect_confidence"], 4),
            "detection_mode": "multimodal",
            "affect_source": fused["affect_source"],
            "facial_confidence": round(fused["facial_confidence"], 4),
            "behavioral_confidence": round(fused["behavioral_confidence"], 4),
            "weights": {k: round(v, 4) for k, v in fused["weights"].items()},
            "forced_mode": mode,
        },
    })


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
    accept_ms = _now_ms()

    superseded, session_id = await connection_manager.connect(user_id, websocket)

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

            if msg_type == "facial_features":
                await _handle_facial_features(envelope, user_id, session_id, db)
                continue

            if msg_type == "behavioral_window":
                await _handle_behavioral_window(envelope, user_id, session_id, db)
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
        fusion_buffer.clear_session(session_id)  # don't leak paired-modality results
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
