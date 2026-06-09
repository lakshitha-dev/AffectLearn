"""Facial affect detection (Story 4.4).

Thin async wrapper over the ONNX engagement inference service
(`app.services.model_inference`). The WebSocket handler calls `detect_engagement`
once per 30s cycle when a `facial_features` message arrives.

The full LangGraph node (operating on `AgentState`) will wrap this once the graph
is built; until then the WS handler invokes it directly. ONNX inference is
CPU-bound and synchronous, so it is offloaded to a worker thread to avoid blocking
the event loop.
"""

import asyncio
from typing import Any

import structlog

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
