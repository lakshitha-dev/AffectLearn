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

Inbound message types handled by the loop: `heartbeat`, `client_hello`, `facial_features`,
`behavioral_window`, (Story 5.6, FR22) `adaptation_interaction` — the client records that
the learner accepted/dismissed/applied a delivered adaptation, which is emitted as a research
event for the Learner Profiler to refine future decisions — and (Story 6.2) `self_report` —
the learner's ground-truth affect label (or a deliberate skip) at a natural pause point,
emitted as a research event for model validation. Malformed inbound is logged + dropped
without ever crashing the loop (NFR22).
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
from app.services import fusion_buffer, study_service
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


async def _resolve_phase_group(db: AsyncSession | None, user_id: str) -> tuple[str, str]:
    """Resolve the learner's (phase, group) ONCE per connection (Story 6.1 — keystone).

    The current global study `phase` and the account-level A/B `group` are read here, at
    handshake, and reused for the connection's lifetime — NOT per cycle — so the hot path
    keeps no extra DB round-trip and stays within the latency budget. The freshness
    trade-off is intentional: a coordinator-driven phase toggle takes effect on the
    learner's NEXT session/reconnect, which is acceptable for a scheduled pilot.

    These real values flow into `make_initial_state(phase=, group=)`, so `AgentState.phase`
    /`AgentState.group` carry real values every cycle and the existing `should_adapt`
    router selects the correct branch — without any router/topology change. This is the
    wiring that finally turns Epic 5's adaptive branch on in production.

    Resolution failure (DB error / no session) degrades SAFELY to `("phase_a","control")` —
    the non-adaptive, never-cross-contaminating default — and is logged (NFR22). A glitch
    must never accidentally route a learner onto the adaptive branch.
    """
    if db is None:
        return ("phase_a", "control")
    try:
        group = await study_service.get_group(db, user_id)
        phase = await study_service.get_phase(db)
        return (phase, group)
    except Exception:
        logger.exception("phase_group_resolution_failed", user_id=user_id)
        return ("phase_a", "control")


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
    envelope: dict[str, Any],
    user_id: str,
    session_id: str,
    db: AsyncSession | None = None,
    phase: str = "phase_a",
    group: str = "control",
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
            phase=phase,
            group=group,
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
        "phase": phase,
        "group": group,
        "payload": payload,
    })

    if result_state is not None and result_state.get("affect_state"):
        await _maybe_fuse("facial", result_state.get("facial_inference") or {},
                          user_id, session_id, cycle, phase, group)

    # Story 5.3: push any adaptation the Phase B cycle produced (no-op for no_action /
    # Phase A — `result_state` then carries no `delivery_message`).
    await _deliver_adaptation(result_state, user_id, session_id, cycle, phase, group)


async def _handle_behavioral_window(
    envelope: dict[str, Any],
    user_id: str,
    session_id: str,
    db: AsyncSession | None = None,
    phase: str = "phase_a",
    group: str = "control",
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
            phase=phase,
            group=group,
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
        "phase": phase,
        "group": group,
        "payload": payload,
    })

    if result_state is not None and result_state.get("affect_state"):
        await _maybe_fuse("behavioral", result_state.get("behavioral_inference") or {},
                          user_id, session_id, cycle, phase, group)

    # Story 5.3: push any adaptation the Phase B cycle produced (no-op for no_action /
    # Phase A — `result_state` then carries no `delivery_message`).
    await _deliver_adaptation(result_state, user_id, session_id, cycle, phase, group)


async def _maybe_fuse(
    modality: str, inference: dict[str, Any], user_id: str, session_id: str, cycle: int,
    phase: str = "phase_a", group: str = "control",
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
        "phase": phase,
        "group": group,
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


async def _deliver_adaptation(
    result_state: dict[str, Any] | None, user_id: str, session_id: str, cycle: int,
    phase: str = "phase_a", group: str = "control",
) -> None:
    """Push the cycle's `adaptation` message to the learner socket (Story 5.3).

    Reads the wire payload the socket-free `deliver_node` built into
    `result_state["delivery_message"]` and sends it verbatim over the SAME learner
    socket via `connection_manager.send_to` — a single direct push, no DB hop, no
    intermediary (NFR2 <100ms). `send_to` returns False when either the socket is
    gone (user disconnected mid-cycle) or a send_json exception was raised + swallowed
    internally; on exception it logs at ERROR level. Either way a dead socket never
    crashes the cycle or the WS loop (architecture lines 335, 647; NFR22).

    A `no_action` / Phase A / control / log_only / empty cycle carries no
    `delivery_message`, so this early-returns: no send, no `adaptation_delivered`
    event (AC3). On a successful push it emits a non-blocking `adaptation_delivered`
    research event via `_safe_emit` (sourced from `adaptation_content.metadata`).
    """
    if result_state is None:
        return
    delivery_message = result_state.get("delivery_message")
    if not delivery_message:
        return

    sent = await connection_manager.send_to(user_id, delivery_message)
    if not sent:
        # Socket gone or send failed — degrade gracefully. Log at debug level so
        # the delivery attempt is visible in traces without flooding normal operation.
        logger.debug(
            "adaptation_delivery_skipped",
            user_id=user_id,
            session_id=session_id,
            cycle=cycle,
            action=delivery_message.get("action"),
            reason="socket_unavailable_or_send_failed",
        )
        return

    metadata = (result_state.get("adaptation_content") or {}).get("metadata") or {}
    await _safe_emit({
        "event_type": "adaptation_delivered",
        "learner_id": user_id,
        "session_id": session_id,
        "cycle_number": cycle,
        "timestamp": _now_ms(),
        "phase": phase,
        "group": group,
        "payload": {
            "action": delivery_message.get("action"),
            "variant": (delivery_message.get("content") or {}).get("variant"),
            "generated": bool(metadata.get("generated")),
            "fallback": bool(metadata.get("fallback")),
        },
    })


_VALID_INTERACTIONS = {"dismissed", "accepted", "applied"}


async def _handle_adaptation_interaction(
    envelope: dict[str, Any], user_id: str, session_id: str,
    phase: str = "phase_a", group: str = "control",
) -> None:
    """Emit a research event for an inbound `adaptation_interaction` message (Story 5.6, FR22).

    The client sends this when the learner accepts/dismisses/applies a delivered adaptation
    (e.g. dismissing a `skip_ahead` suggestion). It is turned into a durable, sequence-numbered
    `adaptation_interaction` research event via `_safe_emit` so the Learner Profiler (4.5) can
    refine future decisions. Follows the standard envelope exactly (snake_case, `_now_ms()`).

    Never raises (NFR22): a malformed/partial message (missing `data`, unknown `interaction`)
    is logged via `ws_invalid_message` and dropped — it must never crash the WS loop.
    """
    data = envelope.get("data")
    if not isinstance(data, dict):
        logger.warning(
            "ws_invalid_message",
            user_id=user_id,
            reason="adaptation_interaction_missing_data",
        )
        return

    interaction = data.get("interaction")
    if interaction not in _VALID_INTERACTIONS:
        logger.warning(
            "ws_invalid_message",
            user_id=user_id,
            reason="adaptation_interaction_invalid_interaction",
        )
        return

    await _safe_emit({
        "event_type": "adaptation_interaction",
        "learner_id": user_id,
        "session_id": session_id,
        "cycle_number": int(data.get("cycle_number", 0) or 0),
        "timestamp": _now_ms(),
        "phase": phase,
        "group": group,
        "payload": {
            "adaptation_id": data.get("adaptation_id"),
            "action": data.get("action"),
            "interaction": interaction,
        },
    })


# Story 6.2: the 5-value self-report ground-truth vocabulary. This is `AFFECT_STATES`
# (`app.agents.state`, the 4 MODEL categories: bored/confused/engaged/frustrated) PLUS
# `neutral` — a deliberate ground-truth SUPERSET. Neutral is a self-report-only label, NOT a
# model output; do NOT import/mutate `AFFECT_STATES` (a learner who feels none of the 4 has a
# real, researchable state). The 5↔4 reconciliation is a downstream research-analysis concern.
_SELF_REPORT_AFFECTS = {"engaged", "confused", "bored", "frustrated", "neutral"}


async def _handle_self_report(
    envelope: dict[str, Any], user_id: str, session_id: str,
    phase: str = "phase_a", group: str = "control",
) -> None:
    """Emit a research event for an inbound `self_report` message (Story 6.2).

    The self-report twin of `_handle_adaptation_interaction`. The client sends this at a
    natural pause point with the learner's GROUND-TRUTH affect label, so the research team can
    validate (and, in Phase A, train) the facial CNN-LSTM / behavioral Bi-LSTM models against
    the learner's own report. It is turned into a durable, sequence-numbered `self_report`
    research event via `_safe_emit` (standard envelope, snake_case, `_now_ms()`). No
    synchronous DB write is added — the Story 4.7 worker drains the event to `research_events`;
    there is NO dedicated `self_reports` table (the research event IS the durable record).

    Vocabulary: `affect` ∈ `_SELF_REPORT_AFFECTS` (the 4 model `AFFECT_STATES` + `neutral`),
    a deliberate 5-value superset. Neutral is self-report-only ground truth, never a model
    output.

    Skip vs missing data: a DELIBERATE skip is `{skipped: true, affect: null}` — the learner
    chose not to answer. A prompt the learner never reached emits NOTHING. Downstream
    (6.5 / 8.6) can therefore separate "chose not to answer" from "was never prompted".

    Never raises (NFR22): a malformed/partial message (missing `data`, an out-of-vocab
    `affect` on a non-skip) is logged via `ws_invalid_message` and dropped — it must never
    crash the WS loop or be persisted.
    """
    data = envelope.get("data")
    if not isinstance(data, dict):
        logger.warning(
            "ws_invalid_message",
            user_id=user_id,
            reason="self_report_missing_data",
        )
        return

    skipped = bool(data.get("skipped"))
    # Pre-pilot control (#7): a due prompt RANDOMLY OMITTED by the client (never shown to the
    # learner) so analysis can estimate the prompt's own reactive effect. It carries no affect
    # and is NOT a user skip; recorded with `omitted:true` so it is distinguishable from both.
    omitted = bool(data.get("omitted"))
    affect = data.get("affect")

    # A valid message is a deliberate skip, an omitted prompt (both affect-less), OR a real
    # selection whose `affect` is in the 5-value vocabulary. Anything else is dropped.
    if not skipped and not omitted and affect not in _SELF_REPORT_AFFECTS:
        logger.warning(
            "ws_invalid_message",
            user_id=user_id,
            reason="self_report_invalid_affect",
        )
        return

    await _safe_emit({
        "event_type": "self_report",
        "learner_id": user_id,
        "session_id": session_id,
        "cycle_number": int(data.get("cycle_number", 0) or 0),
        "timestamp": _now_ms(),
        "phase": phase,
        "group": group,
        "payload": {
            "affect": None if (skipped or omitted) else affect,
            "skipped": skipped,
            "omitted": omitted,
            "prompt_index": data.get("prompt_index"),
            "section_id": data.get("section_id"),
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

    # Story 6.1 (keystone): resolve the learner's real A/B group + the current global study
    # phase ONCE here, at handshake, and reuse them for every cycle this connection runs.
    # This is what feeds real values into `make_initial_state` so the existing router can
    # select the adaptive branch in production (vs the phase_a/control defaults). A toggle
    # therefore takes effect on the learner's next reconnect (acceptable freshness trade-off
    # for a coordinator-driven pilot; protects the per-cycle latency budget — see AC6).
    phase, group = await _resolve_phase_group(db, user_id)

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
            "phase": phase,
            "group": group,
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
        "phase": phase,
        "group": group,
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
                await _handle_facial_features(
                    envelope, user_id, session_id, db, phase, group
                )
                continue

            if msg_type == "behavioral_window":
                await _handle_behavioral_window(
                    envelope, user_id, session_id, db, phase, group
                )
                continue

            if msg_type == "adaptation_interaction":
                # Story 5.6 (FR22): record the learner's accept/dismiss/apply of a delivered
                # adaptation as a research event for the Learner Profiler. Never raises.
                await _handle_adaptation_interaction(
                    envelope, user_id, session_id, phase, group
                )
                continue

            if msg_type == "self_report":
                # Story 6.2: record the learner's ground-truth affect label (or deliberate
                # skip) at a natural pause point as a research event for model validation.
                # Never raises.
                await _handle_self_report(envelope, user_id, session_id, phase, group)
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
            "phase": phase,
            "group": group,
            "payload": {
                "reason": close_reason,
                "duration_ms": _now_ms() - accept_ms,
            },
        })
