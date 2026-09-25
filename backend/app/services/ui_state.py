"""Storage for the per-learner screen state the delivery guard reads (`agents/delivery_guard.py`).

One small JSON document per learner in Redis. Best-effort in every direction: with Redis down the
load returns `{}`, the guard then applies no holds, and the loop behaves exactly as it did before
this existed -- a missing UI state can cost the learner some polish, never an intervention.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from app.services import redis_service

logger = structlog.get_logger(__name__)

#: Matches the session-state TTL in `routes/ws.py`: one sitting.
_TTL_SECONDS = 12 * 60 * 60


def _key(learner_id: Any) -> str:
    return f"ui:learner:{learner_id}"


async def load(learner_id: Any) -> dict[str, Any]:
    """The learner's screen state, or `{}`. Never raises."""
    if not learner_id:
        return {}
    try:
        value = await redis_service.get_json(_key(learner_id))
    except Exception:  # noqa: BLE001
        logger.warning("ui_state_load_failed", exc_info=True)
        return {}
    return value if isinstance(value, dict) else {}


async def update(
    learner_id: Any, change: Callable[[dict[str, Any]], dict[str, Any]]
) -> dict[str, Any]:
    """Read, apply a pure `change`, write back. Returns the new state. Never raises."""
    current = await load(learner_id)
    try:
        new = change(current)
    except Exception:  # noqa: BLE001 -- a bad event must not break the socket loop
        logger.warning("ui_state_change_failed", exc_info=True)
        return current
    if not learner_id:
        return new
    try:
        await redis_service.set_json(_key(learner_id), new, ttl_seconds=_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        logger.warning("ui_state_save_failed", exc_info=True)
    return new
