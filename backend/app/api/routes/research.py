"""Authed (admin) research export/query API (Story 6.5).

Read-only endpoints over the durable `research_events` dataset, all gated by
`require_role(Role.admin)`. They expose the 4.7 pipeline's data for FYRP thesis analysis:

  - GET /admin/research/events         — sequence-ordered, filterable, paginated events.
  - GET /admin/research/events/gaps    — per-session missing sequence numbers (NFR23).
  - GET /admin/research/phase-a-dataset — behavioral feature windows + self-report labels for
                                          Phase A (both groups), for assembling the Bi-LSTM set.

Events are ordered by `(session_id, sequence_number NULLS LAST, timestamp)` — monotonic
per-session sequence order. Responses are camelCase (`CamelModel`). No file generation here
(CSV/JSON file-download UI is Epic 8 / Story 8.5); this is the JSON query/export backend it
consumes. `eventType` accepts a comma-separated list (e.g. `eventType=self_report,quiz_submitted`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.models.user import Role, User
from app.schemas.research_export import (
    ResearchEventOut,
    ResearchEventPage,
    SequenceGapsOut,
)
from app.services import gate_replay_service, research_export_service

router = APIRouter()


def _parse_event_types(event_type: str | None) -> list[str] | None:
    """Split a comma-separated `eventType` query value into a clean list (or None)."""
    if not event_type:
        return None
    types = [t.strip() for t in event_type.split(",") if t.strip()]
    return types or None


@router.get(
    "/research/events",
    response_model=ResearchEventPage,
    tags=["research"],
)
async def list_research_events(
    learner_id: str | None = Query(default=None, alias="learnerId"),
    session_id: str | None = Query(default=None, alias="sessionId"),
    phase: str | None = Query(default=None),
    group: str | None = Query(default=None),
    event_type: str | None = Query(default=None, alias="eventType"),
    start_ts: int | None = Query(default=None, alias="startTs"),
    end_ts: int | None = Query(default=None, alias="endTs"),
    course_id: str | None = Query(default=None, alias="courseId"),
    section_id: str | None = Query(default=None, alias="sectionId"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000, alias="pageSize"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(Role.admin)),
) -> ResearchEventPage:
    """Return sequence-ordered, filterable, paginated research events (admin only)."""
    result = await research_export_service.query_events(
        db,
        learner_id=learner_id,
        session_id=session_id,
        phase=phase,
        group=group,
        event_types=_parse_event_types(event_type),
        start_ts=start_ts,
        end_ts=end_ts,
        course_id=course_id,
        section_id=section_id,
        page=page,
        page_size=page_size,
    )
    return ResearchEventPage(
        items=[ResearchEventOut(**e) for e in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get(
    "/research/events/gaps",
    response_model=SequenceGapsOut,
    tags=["research"],
)
async def research_event_gaps(
    learner_id: str | None = Query(default=None, alias="learnerId"),
    session_id: str | None = Query(default=None, alias="sessionId"),
    phase: str | None = Query(default=None),
    group: str | None = Query(default=None),
    event_type: str | None = Query(default=None, alias="eventType"),
    start_ts: int | None = Query(default=None, alias="startTs"),
    end_ts: int | None = Query(default=None, alias="endTs"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(Role.admin)),
) -> SequenceGapsOut:
    """Per-session missing sequence numbers (NFR23) for the filtered events (admin only)."""
    gaps = await research_export_service.gaps(
        db,
        learner_id=learner_id,
        session_id=session_id,
        phase=phase,
        group=group,
        event_types=_parse_event_types(event_type),
        start_ts=start_ts,
        end_ts=end_ts,
    )
    return SequenceGapsOut(gaps=gaps)


@router.get(
    "/research/phase-a-dataset",
    response_model=ResearchEventPage,
    tags=["research"],
)
async def phase_a_dataset(
    learner_id: str | None = Query(default=None, alias="learnerId"),
    session_id: str | None = Query(default=None, alias="sessionId"),
    start_ts: int | None = Query(default=None, alias="startTs"),
    end_ts: int | None = Query(default=None, alias="endTs"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000, alias="pageSize"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(Role.admin)),
) -> ResearchEventPage:
    """Phase A training set: behavioral feature windows + self-report labels (both groups).

    Join key for the analyst: pair each `behavioral_affect_detected` window to a `self_report`
    label by `session_id` + the nearest preceding `cycle_number`/`timestamp`. Behavioral payload
    carries `event_counts`/`idle`, raw model output (`label`/`probs`/`n_bins`/`affect_*`), and the
    aggregate `features` window (n_bins × N_FEATURES) — the Bi-LSTM training input (guide §7); the
    self_report payload carries `{affect, skipped, omitted, prompt_index, section_id}` (an
    `omitted:true` row is a due prompt randomly withheld for reactivity estimation, not a skip).
    """
    result = await research_export_service.phase_a_dataset(
        db,
        learner_id=learner_id,
        session_id=session_id,
        start_ts=start_ts,
        end_ts=end_ts,
        page=page,
        page_size=page_size,
    )
    return ResearchEventPage(
        items=[ResearchEventOut(**e) for e in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/research/gate-replay", tags=["research"])
async def gate_replay(
    floors: str = Query(
        default="0.50,0.55,0.60,0.65,0.70,0.75,0.80",
        description="Comma-separated confidence floors to sweep.",
    ),
    min_consecutive: int | None = Query(default=None, ge=1, le=10, alias="minConsecutive"),
    cooldown_cycles: int | None = Query(default=None, ge=0, le=60, alias="cooldownCycles"),
    decisive_sources: str | None = Query(default=None, alias="decisiveSources"),
    phase: str | None = Query(default=None),
    group: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(Role.admin)),
):
    """What the adaptation gate WOULD have done at other settings, over the recorded cycles.

    Section 7.4 records why this exists: the deployed thresholds were calibrated on out-of-fold
    predictions from a corpus of business-software users, and inherit two artefacts from that
    simulation. It also records the fix -- the gate now logs a reason for every withheld cycle,
    so the calibration can be repeated on real ones.

    `decisiveSources` is the parameter that answers a live question: pass it including
    `performance` to see how often the behaviour-driven channel WOULD have intervened if it were
    promoted from advisory, before promoting it.

    Settings not swept default to the DEPLOYED configuration, so a sweep varies one thing at a
    time against what is actually running rather than an invented baseline.
    """
    try:
        parsed = [float(f) for f in floors.split(",") if f.strip()]
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "INVALID_FLOORS",
                              "message": "floors must be comma-separated numbers"}},
        ) from None
    if not parsed or len(parsed) > 25:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "INVALID_FLOORS",
                              "message": "supply between 1 and 25 floors"}},
        )

    sources = (
        [s.strip() for s in decisive_sources.split(",") if s.strip()]
        if decisive_sources is not None
        else None
    )

    return await gate_replay_service.sweep(
        db,
        confidence_floors=parsed,
        min_consecutive=min_consecutive,
        cooldown_cycles=cooldown_cycles,
        decisive_sources=sources,
        phase=phase,
        group=group,
    )
