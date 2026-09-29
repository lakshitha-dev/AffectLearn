"""Facilitator records for the in-person pilot: one row per participant sitting (migration 034).

Mounted under `/admin`. Admin-only. The facilitator starts a sitting when the participant sits down
(after consent) and ends it when they leave, with the reason -- completed, withdrawn, technical --
and any deviation from the protocol. The arm, phase, consent version and configuration version are
read from the system at the start rather than typed, so the record cannot disagree with what the
participant was actually given.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.models.pilot_session import END_REASONS, PilotSession
from app.models.user import Role, User
from app.schemas.base import CamelModel
from app.services import config_service, study_service
from app.services.research_logger import emit as emit_research_event

router = APIRouter()


class PilotSessionStart(CamelModel):
    user_id: uuid.UUID
    participant_code: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9_-]+$")
    protocol_version: str | None = Field(default=None, max_length=32)
    device: dict[str, Any] | None = None


class PilotSessionEnd(CamelModel):
    end_reason: str
    deviation_notes: str | None = Field(default=None, max_length=4000)


class PilotSessionOut(CamelModel):
    id: str
    user_id: str
    participant_code: str
    group: str | None = None
    phase: str | None = None
    protocol_version: str | None = None
    consent_version: str | None = None
    config_version_at_start: int | None = None
    device: dict[str, Any] | None = None
    started_at: str
    ended_at: str | None = None
    end_reason: str | None = None
    deviation_notes: str | None = None


def _out(row: PilotSession) -> PilotSessionOut:
    return PilotSessionOut(
        id=str(row.id), user_id=str(row.user_id), participant_code=row.participant_code,
        group=row.group, phase=row.phase, protocol_version=row.protocol_version,
        consent_version=row.consent_version, config_version_at_start=row.config_version_at_start,
        device=row.device, started_at=row.started_at.isoformat(),
        ended_at=row.ended_at.isoformat() if row.ended_at else None,
        end_reason=row.end_reason, deviation_notes=row.deviation_notes,
    )


async def _emit(event_type: str, row: PilotSession, extra: dict[str, Any]) -> None:
    try:
        await emit_research_event({
            "event_type": event_type,
            "learner_id": str(row.user_id),
            "session_id": None,
            "cycle_number": 0,
            "timestamp": int(time.time() * 1000),
            "phase": row.phase,
            "group": row.group,
            "payload": {"pilot_session_id": str(row.id),
                        "participant_code": row.participant_code, **extra},
        })
    except Exception:  # noqa: BLE001 — the row is the durable record
        pass


@router.post("/pilot/sessions", response_model=PilotSessionOut,
             status_code=status.HTTP_201_CREATED)
async def start_pilot_session(
    body: PilotSessionStart,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.admin)),
):
    participant = await db.get(User, body.user_id)
    if participant is None or participant.role != Role.learner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "error": {"code": "NOT_FOUND", "message": "No such learner"}})
    row = PilotSession(
        user_id=participant.id,
        participant_code=body.participant_code,
        group=await study_service.get_group(db, participant.id),
        phase=await study_service.get_phase(db),
        protocol_version=body.protocol_version,
        consent_version=participant.consent_version,
        config_version_at_start=config_service.get_version(),
        device=body.device,
        started_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await _emit("pilot_session_started", row, {
        "protocol_version": row.protocol_version,
        "config_version_at_start": row.config_version_at_start,
    })
    return _out(row)


@router.post("/pilot/sessions/{session_id}/end", response_model=PilotSessionOut)
async def end_pilot_session(
    session_id: uuid.UUID,
    body: PilotSessionEnd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.admin)),
):
    if body.end_reason not in END_REASONS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "error": {"code": "INVALID_END_REASON",
                      "message": f"end_reason must be one of {', '.join(END_REASONS)}"}})
    row = await db.get(PilotSession, session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "error": {"code": "NOT_FOUND", "message": "No such pilot session"}})
    if row.ended_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
            "error": {"code": "ALREADY_ENDED", "message": "This sitting has already ended"}})
    row.ended_at = datetime.now(timezone.utc)
    row.end_reason = body.end_reason
    row.deviation_notes = body.deviation_notes
    await db.commit()
    await db.refresh(row)
    await _emit("pilot_session_ended", row, {"end_reason": row.end_reason})
    return _out(row)


@router.get("/pilot/sessions", response_model=list[PilotSessionOut])
async def list_pilot_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.admin)),
):
    rows = (await db.execute(select(PilotSession).order_by(PilotSession.started_at))).scalars().all()
    return [_out(r) for r in rows]
