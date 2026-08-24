"""Observability dashboard API (Monitor).

Admin-only. Exposes the in-process monitor bus to a dashboard via Server-Sent Events
plus REST helpers (recent events, active sessions, graph topology, component health).

The SSE endpoint authenticates with a JWT in the query string because `EventSource`
cannot set headers — this mirrors the WebSocket endpoint's handshake. The REST
endpoints use the normal `Authorization: Bearer` header via `require_role`.
"""

from __future__ import annotations

import asyncio
import json
import uuid as uuid_mod

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from jose import JWTError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.core.security import decode_token
from app.models.user import Role, User
from app.services import redis_service
from app.services.connection_manager import connection_manager
from app.services import llm_health, monitor_aggregate_service
from app.services.model_report import model_report
from app.services.monitor_bus import monitor_bus

logger = structlog.get_logger(__name__)

router = APIRouter()

# Static graph topology — the single source of truth for the dashboard flow diagram.
# `kind: "stub"` marks pass-through nodes (Story 5.x) so the UI never implies real work.
_GRAPH_TOPOLOGY: dict = {
    "nodes": [
        {"id": "affect_detection", "label": "Affect Detection", "kind": "active",
         "desc": "Facial CNN-LSTM (binary confusion) / behavioural GBDT → confused vs engaged. "
                 "Fusion of the two runs in the WS handler BEFORE the graph, not as a node here"},
        {"id": "learner_profiler", "label": "Learner Profiler", "kind": "active",
         "desc": "Fold affect into profile (Redis hot + Postgres cold)"},
        {"id": "log_only", "label": "Log Only", "kind": "active",
         "desc": "Phase A / control terminal — no adaptation"},
        {"id": "pedagogical", "label": "Pedagogical Strategist", "kind": "active",
         "desc": "vLLM strategy decision → rule-based fallback (Story 5.1)"},
        {"id": "content_adapter", "label": "Content Adapter", "kind": "active",
         "desc": "vLLM content generation → rule-based fallback (Story 5.2)"},
        {"id": "deliver", "label": "Deliver", "kind": "active",
         "desc": "Build adaptation wire payload → WS handler pushes to client (Story 5.3)"},
    ],
    "edges": [
        {"from": "START", "to": "affect_detection"},
        {"from": "affect_detection", "to": "learner_profiler"},
        {"from": "learner_profiler", "to": "log_only", "kind": "conditional", "route": "log_only"},
        {"from": "learner_profiler", "to": "pedagogical", "kind": "conditional", "route": "pedagogical"},
        {"from": "pedagogical", "to": "content_adapter"},
        {"from": "content_adapter", "to": "deliver"},
        {"from": "deliver", "to": "END"},
        {"from": "log_only", "to": "END"},
    ],
}


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "INVALID_TOKEN", "message": "Could not validate credentials"}},
    )


async def _require_admin_sse(
    token: str = Query(..., description="access JWT (EventSource cannot set headers)"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate a query-string access token and require the admin role (for SSE).

    Uses the standard `get_db` dependency so it is overridable in tests. The session is
    held for the stream's lifetime but stays idle — acceptable for a low-traffic
    admin-only endpoint.
    """
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise _unauthorized()
        uid = uuid_mod.UUID(payload.get("sub"))
    except (JWTError, ValueError, AttributeError, TypeError):
        raise _unauthorized()

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise _unauthorized()
    if user.role != Role.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": "Admin only"}},
        )
    return user


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


@router.get("/stream")
async def stream(
    request: Request,
    session_id: str | None = Query(None),
    _admin: User = Depends(_require_admin_sse),
):
    """Server-Sent Events stream of live monitor events (backlog first, then live)."""
    queue = monitor_bus.subscribe()

    async def gen():
        try:
            for ev in monitor_bus.recent(session_id=session_id, limit=200):
                yield _sse(ev)
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"  # comment frame keeps the connection warm
                    continue
                if session_id and ev.get("session_id") != session_id:
                    continue
                yield _sse(ev)
        finally:
            monitor_bus.unsubscribe(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering so events flush immediately
        },
    )


@router.get("/events")
async def recent_events(
    session_id: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    _: User = Depends(require_role(Role.admin)),
):
    """Recent buffered events for initial dashboard load / non-SSE fallback."""
    return {"events": monitor_bus.recent(session_id=session_id, limit=limit)}


@router.get("/sessions")
async def sessions(_: User = Depends(require_role(Role.admin))):
    """Active WS sessions plus session ids seen in the recent event buffer."""
    return {
        "active": connection_manager.active_sessions(),
        "recent_session_ids": monitor_bus.session_ids(),
    }


@router.get("/graph")
async def graph(_: User = Depends(require_role(Role.admin))):
    """Static agent-graph topology for the flow diagram (active vs stub nodes)."""
    return _GRAPH_TOPOLOGY


@router.get("/aggregates")
async def aggregates(
    hours: int = Query(24, ge=1, le=720, description="look-back window in hours"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(Role.admin)),
):
    """Pipeline behaviour over a window: gate-reason distribution, rate, fallback share.

    The live stream shows single cycles; this shows whether the gate is calibrated. See
    `monitor_aggregate_service` for why payload extraction happens in Python.
    """
    return await monitor_aggregate_service.aggregates(db, hours=hours)


@router.get("/health")
async def health(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(Role.admin)),
):
    """Real component health (replaces the mock System Health data)."""
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    # Same report `/health/pipeline` serves, so the dashboard and the liveness probe can never
    # disagree. `available` is kept alongside `exists` for the existing frontend contract.
    models = model_report()
    for key in ("behavioral", "facial"):
        models[key]["available"] = bool(models[key].get("exists"))

    return {
        "models": models,
        # Whether adaptations are actually GENERATED or coming from the deterministic fallback.
        "llm": await llm_health.probe(),
        "redis": {"enabled": not getattr(redis_service, "_disabled", False)},
        "database": {"ok": db_ok},
        "websocket": {"active_connections": len(connection_manager.active_user_ids())},
        "monitor": {
            "subscribers": monitor_bus.subscriber_count(),
            "buffered_events": monitor_bus.size(),
        },
    }
