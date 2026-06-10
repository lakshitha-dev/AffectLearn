"""Facial affect detection — LangGraph node + inference wrapper (Story 4.4).

`detect_engagement` is the thin async wrapper over the ONNX engagement service
(`app.services.model_inference`); it is reused unchanged and stays covered by its
own tests. `affect_detection_node` is the LangGraph node (Story 4.4): it pulls the
per-cycle facial payload from `AgentState`, runs inference off the event loop, and
writes the affect CATEGORY (`affect_state`) plus provenance into state.

The node always writes one of the four affect categories to `affect_state` (never an
engagement level) via `app.agents.affect_mapping` — see Story 4.4 Dev Notes.

ONNX inference is CPU-bound and synchronous, so it is offloaded to a worker thread
to avoid blocking the event loop.
"""

import asyncio
from typing import Any

import structlog

from app.agents.affect_mapping import resolve_affect
from app.agents.state import AFFECT_SOURCE_BEHAVIORAL, AgentState
from app.services.behavioral_inference import predict_from_window
from app.services.model_inference import predict_from_payload

logger = structlog.get_logger(__name__)


async def detect_engagement(data: dict[str, Any]) -> dict[str, Any] | None:
    """Run engagement inference for one `facial_features` cycle payload.

    `data` is the `facial_features` message's `data` object (snake_case):
    `frames_b64`, `frames_captured`, `dropped_frames`, `cycle_number`, ...

    Returns the inference dict (`engagement_level`, `label`, `confidence`,
    `probs`, `frames_used`) or None for an empty cycle (no face detected the
    whole window) — in which case the caller falls back to behavioural-only
    weighting for that cycle.
    """
    frames_b64 = data.get("frames_b64", "") or ""
    frames_captured = int(data.get("frames_captured", 0) or 0)
    if frames_captured <= 0 or not frames_b64:
        return None
    return await asyncio.to_thread(predict_from_payload, frames_b64, frames_captured)


def _resolve_detection_mode(state: AgentState) -> str:
    """Which modalities fed this cycle, from the payloads present in `state`.

    Story 4.4 sends one `facial_payload` per cycle; Story 4.4b sends one
    `behavioral_payload`. Seam for Story 4.4c: when BOTH are present, return
    `"multimodal"` and late-fuse. For now facial takes precedence if both are somehow
    present (each upstream handler seeds exactly one modality), so this returns
    `"behavioral_only"` only for a behavioral-only cycle.
    """
    has_facial = bool(state.get("facial_payload"))
    has_behavioral = bool(state.get("behavioral_payload"))
    # TODO Story 4.4c: `if has_facial and has_behavioral: return "multimodal"`
    if has_behavioral and not has_facial:
        return "behavioral_only"
    return "facial_only"


async def _run_facial(state: AgentState, mode: str) -> dict[str, Any]:
    """Facial branch (Story 4.4): CNN-LSTM engagement -> 4-category affect."""
    payload: dict[str, Any] = state.get("facial_payload") or {}
    result = await detect_engagement(payload)

    if result is None:
        logger.info(
            "affect_detection_empty_cycle",
            learner_id=state.get("learner_id"),
            cycle=state.get("cycle_number"),
        )
        return {"detection_mode": mode, "empty_cycle": True}

    affect_state, affect_source, affect_confidence, extra = resolve_affect(result)
    update: dict[str, Any] = {
        "affect_state": affect_state,
        # confidence in the chosen CATEGORY — aggregated across collapsed engagement
        # levels under the adapter (see affect_mapping.category_confidence), not the
        # single argmax prob which would understate it.
        "affect_confidence": affect_confidence,
        "detection_mode": mode,
        "affect_source": affect_source,
        "facial_inference": result,
        **extra,
    }
    logger.info(
        "affect_detected",
        learner_id=state.get("learner_id"),
        cycle=state.get("cycle_number"),
        modality="facial",
        affect_state=affect_state,
        affect_source=affect_source,
        detection_mode=mode,
    )
    return update


async def _run_behavioral(state: AgentState, mode: str) -> dict[str, Any]:
    """Behavioral branch (Story 4.4b): Bi-LSTM -> 4-category affect (native classes).

    Inference runs off the event loop (CPU-bound ONNX). An idle window classifies the
    all-zeros feature window (a valid low-activity input), so a normal behavioral cycle
    always produces an `affect_state`. Inference errors are NOT swallowed here — the WS
    handler boundary maps them to a skipped cycle (NFR22).
    """
    payload: dict[str, Any] = state.get("behavioral_payload") or {}
    events = payload.get("events") or []
    started = int(payload.get("capture_started_at_wall", 0) or 0)
    result = await asyncio.to_thread(predict_from_window, events, started)

    if result is None:  # forward-compat: only a structurally unusable window
        return {"detection_mode": mode, "empty_cycle": True}

    update: dict[str, Any] = {
        "affect_state": result["label"],  # Bi-LSTM emits the 4 categories natively
        "affect_confidence": float(result["confidence"]),
        "detection_mode": mode,
        "affect_source": AFFECT_SOURCE_BEHAVIORAL,
        "behavioral_inference": result,
    }
    logger.info(
        "affect_detected",
        learner_id=state.get("learner_id"),
        cycle=state.get("cycle_number"),
        modality="behavioral",
        affect_state=result["label"],
        affect_source=AFFECT_SOURCE_BEHAVIORAL,
        detection_mode=mode,
    )
    return update


async def affect_detection_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: run affect inference for the present modality and write to state.

    Dispatches by which payload the WS handler seeded: `behavioral_payload` →
    behavioral Bi-LSTM (Story 4.4b), otherwise the facial CNN-LSTM path (Story 4.4).
    Returns a partial state update (LangGraph merges it). Inference errors propagate so
    the WS handler boundary degrades the cycle gracefully (NFR22) without crashing the
    session.
    """
    mode = _resolve_detection_mode(state)
    if mode == "behavioral_only":
        return await _run_behavioral(state, mode)
    return await _run_facial(state, mode)
