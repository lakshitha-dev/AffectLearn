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
import os
from typing import Any

import structlog

from app.agents.affect_mapping import resolve_affect
from app.agents.fusion import fuse_modalities
from app.agents.state import AFFECT_SOURCE_BEHAVIORAL, AgentState
from app.services.behavioral_inference import predict_from_window
from app.services.model_inference import predict_from_payload

logger = structlog.get_logger(__name__)


async def detect_engagement(data: dict[str, Any]) -> dict[str, Any] | None:
    """Run engagement inference for one `facial_features` cycle payload.

    `data` is the `facial_features` message's `data` object (snake_case):
    `frames_b64`, `frames_captured`, `dropped_frames`, `cycle_number`, ...

    Returns the inference dict (`engagement_level`, `label`, `confidence`,
    `probs`, `frames_used`) or None when the cycle contains no USABLE face — in
    which case the caller falls back to behavioural-only weighting for that cycle.

    "No usable face" used to be the same thing as "no frames": faceless frames were
    dropped browser-side, so an absent learner produced `frames_captured == 0`. That
    stopped being true when the capture path started emitting a CENTRE CROP for
    faceless frames to match the training distribution — a necessary change, but it
    meant an empty chair produced a full 16-frame clip and the model returned a
    confident-looking affect reading for nobody, which the adaptation gate could then
    act on.

    So the browser now reports `face_absent` (fewer than `minFaceFrameRatio` of the
    cycle's frames contained a face) and it is honoured here, at the same boundary.
    The centre-crop fallback still covers MOMENTARY detector misses, which is what
    training actually contained.
    """
    frames_b64 = data.get("frames_b64", "") or ""
    frames_captured = int(data.get("frames_captured", 0) or 0)
    if frames_captured <= 0 or not frames_b64:
        return None
    if data.get("face_absent"):
        logger.info(
            "affect_detection_face_absent",
            cycle=data.get("cycle_number"),
            frames_captured=frames_captured,
            frames_with_face=data.get("frames_with_face"),
            face_ratio=data.get("face_ratio"),
        )
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
    # Story 4.4c, decision path. A cycle never carries BOTH payloads — the modalities arrive on
    # separate WS messages — so "multimodal" is signalled by one payload plus a fresh counterpart
    # RESULT from `fusion_buffer`, which the handler seeds. The counterpart's model is not re-run.
    if state.get("counterpart_inference") and fusion_drives_decision():
        return "multimodal"
    if has_behavioral and not has_facial:
        return "behavioral_only"
    return "facial_only"


def fusion_drives_decision() -> bool:
    """Whether the FUSED estimate drives the live decision, or only the research event.

    Default ON. Set FUSION_DRIVES_DECISION=0 to revert to single-modality decisions with fusion
    logged only — which is what this system did before, and which the measured evidence mildly
    favours:

      * On the only genuinely paired data available (DUX), fusing scored AUC 0.728 against 0.747
        for the behavioural channel alone.
      * In an end-to-end replay, pairing the behavioural channel with a WORSE-than-chance facial
        stand-in silenced the system entirely — 0 interventions over 1,419 windows — because every
        fused confidence fell under the gate's floor.
      * `fuse_modalities` weights by each model's SELF-REPORTED confidence, not its measured
        reliability, so the weaker facial channel (AUC 0.641 vs 0.747) can outvote the stronger one
        whenever it happens to be more confident.

    It is ON because a single fused answer is what the pedagogical agent needs, and because the
    alternative — computing fusion and discarding it — meant the "multimodal" claim was never true
    of the decision. The flag exists so this is one env var to undo, and so an A/B can measure it on
    real learners rather than arguing from a different corpus.
    """
    return os.getenv("FUSION_DRIVES_DECISION", "1").strip().lower() not in ("0", "false", "no")


async def _run_multimodal(state: AgentState, mode: str) -> dict[str, Any]:
    """Run the arriving modality, fuse it with the buffered counterpart, write the FUSED state.

    This is the step that was missing: `ws.py` computed a fused estimate and emitted it as a
    research event, but nothing wrote it back, so every pedagogical decision came from one model
    however multimodal the logs looked.

    Falls back to the single-modality result if fusion cannot produce a state, so a malformed
    counterpart degrades to the previous behaviour instead of dropping the cycle.
    """
    counterpart = state.get("counterpart_inference") or {}
    which = state.get("counterpart_modality") or ""
    arriving_behavioral = bool(state.get("behavioral_payload"))

    base = await (_run_behavioral(state, mode) if arriving_behavioral
                  else _run_facial(state, mode))
    if base.get("empty_cycle") or not base.get("affect_state"):
        return base  # nothing to fuse with; the branch already logged why

    own = (base.get("behavioral_inference") if arriving_behavioral
           else base.get("facial_inference")) or {}
    facial_result = counterpart if which == "facial" else own
    behavioral_result = counterpart if which == "behavioral" else own

    try:
        fused = fuse_modalities(facial_result=facial_result, behavioral_result=behavioral_result)
    except Exception:
        logger.exception("fusion_failed_falling_back_to_unimodal",
                         learner_id=state.get("learner_id"), cycle=state.get("cycle_number"))
        return base
    if not fused.get("affect_state"):
        return base

    update = dict(base)
    update.update({
        "affect_state": fused["affect_state"],
        "affect_confidence": float(fused["affect_confidence"]),
        "affect_source": fused["affect_source"],
        "detection_mode": "multimodal",
        "fusion_applied": True,
        "fusion_weights": fused.get("weights") or {},
    })
    logger.info(
        "affect_fused",
        learner_id=state.get("learner_id"), cycle=state.get("cycle_number"),
        arriving="behavioral" if arriving_behavioral else "facial", counterpart=which,
        unimodal_state=base.get("affect_state"),
        unimodal_confidence=round(float(base.get("affect_confidence", 0.0)), 4),
        fused_state=fused["affect_state"],
        fused_confidence=round(float(fused["affect_confidence"]), 4),
        changed=base.get("affect_state") != fused["affect_state"],
    )
    return update


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
    When the handler also seeded a fresh `counterpart_inference` from `fusion_buffer` and
    FUSION_DRIVES_DECISION is on, the arriving modality is fused with it and the FUSED
    estimate becomes `affect_state` (Story 4.4c).
    Returns a partial state update (LangGraph merges it). Inference errors propagate so
    the WS handler boundary degrades the cycle gracefully (NFR22) without crashing the
    session.
    """
    mode = _resolve_detection_mode(state)
    if mode == "multimodal":
        return await _run_multimodal(state, mode)
    if mode == "behavioral_only":
        return await _run_behavioral(state, mode)
    return await _run_facial(state, mode)
