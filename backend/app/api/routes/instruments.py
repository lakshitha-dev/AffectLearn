"""Pilot questionnaires: lesson feedback, SUS and UEQ-S (migration 034, `services/instruments.py`).

`POST /instruments/{instrument}` stores one administration for the authenticated learner and emits
an `instrument_submitted` research event, so the answer sits on the same timeline as the readings
and adaptations it is about. `GET /instruments/mine` lists what the learner has already answered,
so the lesson page does not ask twice about the same lesson.

Learner-only, like the other questionnaires: a designer or admin clicking through a form while
testing must not leave a row that looks like a participant's. A learner who has not consented, or
has withdrawn, is refused -- these answers are research data.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.models.instrument_response import InstrumentResponse
from app.models.user import Role, User
from app.schemas.base import CamelModel
from app.services.consent import ConsentState
from app.services.instruments import INSTRUMENTS, sus_score, ueq_s_scales
from app.services.research_logger import emit as emit_research_event

logger = structlog.get_logger(__name__)
router = APIRouter()


class InstrumentSubmit(CamelModel):
    instrument_version: str | None = Field(default=None, max_length=16)
    #: Where it was administered, e.g. {"courseId": ..., "lessonId": ...}.
    context: dict[str, Any] | None = None
    responses: dict[str, Any] = Field(default_factory=dict)
    skipped: bool = False
    shown_at: datetime | None = None


class InstrumentOut(CamelModel):
    id: str
    instrument: str
    instrument_version: str
    context: dict[str, Any] | None = None
    skipped: bool
    submitted_at: str


def _out(row: InstrumentResponse) -> InstrumentOut:
    return InstrumentOut(
        id=str(row.id), instrument=row.instrument, instrument_version=row.instrument_version,
        context=row.context, skipped=bool(row.skipped),
        submitted_at=row.submitted_at.isoformat() if row.submitted_at else "",
    )


def _clean_context(context: dict[str, Any] | None) -> dict[str, str] | None:
    """Identifiers only, as short strings -- the context is a join key, not a free-text field."""
    if not context:
        return None
    keep = ("courseId", "moduleId", "lessonId", "course_id", "module_id", "lesson_id")
    out = {k: str(v)[:64] for k, v in context.items() if k in keep and v is not None}
    return out or None


@router.post("/instruments/{instrument}", response_model=InstrumentOut,
             status_code=status.HTTP_201_CREATED)
async def submit_instrument(
    instrument: str,
    body: InstrumentSubmit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    spec = INSTRUMENTS.get(instrument)
    if spec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "error": {"code": "UNKNOWN_INSTRUMENT", "message": f"No instrument '{instrument}'"}})
    if not ConsentState.of(current_user).participating:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
            "error": {"code": "NOT_PARTICIPATING", "message": "Consent is required"}})
    if body.instrument_version and body.instrument_version != spec.version:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "error": {"code": "VERSION_MISMATCH",
                      "message": f"{instrument} is version {spec.version}"}})
    try:
        responses = {} if body.skipped else spec.validate(body.responses)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "error": {"code": "INVALID_RESPONSES", "message": str(exc)}}) from exc

    context = _clean_context(body.context)
    row = InstrumentResponse(
        user_id=current_user.id, instrument=spec.name, instrument_version=spec.version,
        context=context, responses=responses, skipped=body.skipped, shown_at=body.shown_at,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    scores: dict[str, Any] = {}
    if not body.skipped and spec.name == "sus":
        scores["sus_score"] = sus_score(responses)
    if not body.skipped and spec.name == "ueq_s":
        scores["ueq_s"] = ueq_s_scales(responses)
    try:
        await emit_research_event({
            "event_type": "instrument_submitted",
            "learner_id": str(current_user.id),
            "session_id": None,
            "cycle_number": 0,
            "timestamp": int(time.time() * 1000),
            "payload": {
                "instrument": spec.name, "instrument_version": spec.version,
                "context": context, "responses": responses, "skipped": body.skipped,
                "shown_at": body.shown_at.isoformat() if body.shown_at else None,
                **scores,
            },
        })
    except Exception:  # noqa: BLE001 — the row is the durable record
        logger.exception("instrument_event_emit_failed", instrument=spec.name)
    return _out(row)


@router.get("/instruments/mine", response_model=list[InstrumentOut])
async def my_instruments(
    instrument: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
):
    stmt = select(InstrumentResponse).where(InstrumentResponse.user_id == current_user.id)
    if instrument:
        stmt = stmt.where(InstrumentResponse.instrument == instrument)
    rows = (await db.execute(stmt.order_by(InstrumentResponse.submitted_at))).scalars().all()
    return [_out(r) for r in rows]
