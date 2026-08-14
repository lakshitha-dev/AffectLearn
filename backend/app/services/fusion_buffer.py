"""Per-session pairing buffer for multimodal fusion (Story 4.4c AC3).

Facial and behavioral estimates arrive as SEPARATE WebSocket messages on independent 30s
cadences. To late-fuse them (Story 4.4c) we hold the most recent unimodal result per
session and pair it with the counterpart when it arrives within `FUSION_PAIR_WINDOW_MS`.

PRIVACY (NFR10): this buffer stores only the small inference RESULT dicts (probs /
confidence) — never raw frames or behavioral events. Entries are cleared on pairing,
expiry, or session disconnect, so memory stays bounded (≤ 1 slot per modality per session).

In-process module-level state is sufficient: a learner has a single WS connection on one
server (architecture: one connection per learner). A multi-worker deployment would move
this to Redis keyed by session — noted as a forward item, not built now.
"""

from __future__ import annotations

from typing import Any

_MODALITIES = ("facial", "behavioral")

# session_id -> { modality: (result_dict, ts_ms) }
_BUFFER: dict[str, dict[str, tuple[dict[str, Any], int]]] = {}


def record(session_id: str, modality: str, result: dict[str, Any], ts: int) -> None:
    """Store the latest unimodal inference result for a session+modality."""
    if modality not in _MODALITIES:
        raise ValueError(f"unknown modality: {modality}")
    _BUFFER.setdefault(session_id, {})[modality] = (dict(result), int(ts))


def take_counterpart(
    session_id: str, modality: str, now: int, window_ms: int | None = None
) -> dict[str, Any] | None:
    """Return + remove the OTHER modality's recent result, or None if absent/stale."""
    from app.agents.fusion import FUSION_PAIR_WINDOW_MS

    window = FUSION_PAIR_WINDOW_MS if window_ms is None else window_ms
    other = "behavioral" if modality == "facial" else "facial"
    session = _BUFFER.get(session_id)
    if not session or other not in session:
        return None
    result, ts = session.pop(other)
    if int(now) - ts > window:
        return None  # stale — already popped, so it won't linger
    return result


def peek_counterpart(
    session_id: str, modality: str, now: int, window_ms: int | None = None
) -> dict[str, Any] | None:
    """Return the OTHER modality's recent result WITHOUT removing it, or None if absent/stale.

    Needed because the counterpart is now used TWICE per pairing: once to drive the live
    decision (`affect_detection_node` fuses it into `affect_state`) and once to emit the
    `multimodal_affect_detected` research event. `take_counterpart` consumes the slot, so
    calling it for the decision would leave the research event unpaired — the two would
    silently disagree about whether a pair existed.

    A stale entry is left in place rather than popped: this is a read-only probe, and the
    caller that owns consumption (`take_counterpart`) will clear it.
    """
    from app.agents.fusion import FUSION_PAIR_WINDOW_MS

    window = FUSION_PAIR_WINDOW_MS if window_ms is None else window_ms
    other = "behavioral" if modality == "facial" else "facial"
    session = _BUFFER.get(session_id)
    if not session or other not in session:
        return None
    result, ts = session[other]
    if int(now) - ts > window:
        return None
    return dict(result)


def clear_session(session_id: str) -> None:
    """Drop all buffered results for a session (call on WS disconnect)."""
    _BUFFER.pop(session_id, None)


def _reset() -> None:
    """Test helper — clear the whole buffer."""
    _BUFFER.clear()
