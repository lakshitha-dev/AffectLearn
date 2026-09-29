"""Persist the raw events of a behavioural window for a learner who opted in (migration 033).

Called from the `behavioral_window` handler with the message exactly as received. Consent is the
caller's decision (`ConsentState.raw_interaction`); this module only stores. Never raises: losing a
raw window must not cost the learner their cycle, and the derived features are recorded either way.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.raw_interaction_window import RawInteractionWindow

logger = structlog.get_logger(__name__)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def record_window(
    db: AsyncSession | None,
    *,
    learner_id: str,
    session_id: str | None,
    data: dict[str, Any],
    decision_id: str | None,
    received_at_ms: int,
) -> bool:
    """Write one window. Returns whether a row was written."""
    if db is None:
        return False
    try:
        learner_uuid = uuid.UUID(str(learner_id))
    except (TypeError, ValueError):
        logger.warning("raw_window_skipped", reason="learner_id_not_uuid")
        return False
    events = data.get("events")
    try:
        db.add(RawInteractionWindow(
            learner_id=learner_uuid,
            session_id=(str(session_id)[:64] if session_id else None),
            page_instance_id=(str(data["page_instance_id"])[:64]
                              if data.get("page_instance_id") else None),
            cycle_number=_int_or_none(data.get("cycle_number")) or 0,
            decision_id=decision_id,
            section_id=(str(data["section_id"])[:64] if data.get("section_id") else None),
            capture_started_at_wall=_int_or_none(data.get("capture_started_at_wall")),
            capture_ended_at_wall=_int_or_none(data.get("capture_ended_at_wall")),
            received_at_ms=received_at_ms,
            schema_version=_int_or_none(data.get("schema_version")),
            viewport=data.get("viewport") if isinstance(data.get("viewport"), dict) else None,
            events=events if isinstance(events, list) else [],
            ui_events=data.get("ui_events") if isinstance(data.get("ui_events"), list) else None,
            dropped_events=_int_or_none(data.get("dropped_events")) or 0,
            partial=bool(data.get("partial", False)),
        ))
        await db.commit()
        return True
    except Exception:  # noqa: BLE001 — a lost raw window must never break the cycle
        try:
            await db.rollback()
        except Exception:
            pass
        logger.exception("raw_window_write_failed", learner_id=str(learner_id))
        return False
