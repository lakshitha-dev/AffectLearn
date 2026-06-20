"""Learner Profiler node (Story 4.5 — real logic; was a stub in Story 4.4).

Each cycle, after affect detection: load the learner profile (Redis hot → Postgres cold →
pre-assessment-initialized default), fold in the current affect, write through to Redis +
best-effort Postgres (FR31 cross-session continuity), emit a `learner_profile_updated`
research event, and set the `should_adapt` routing flag (preserving the Story 4.4 contract).

Never raises: Redis/DB failures degrade to an in-memory profile so the cycle always
completes (NFR22). The DB session arrives transiently via `state["db"]` (the WS connection's
session); when absent (unit tests / no-DB paths) the node falls back to the default profile.
"""

import os
import time
from typing import Any

import structlog

from app.agents.edges import should_adapt
from app.agents.state import AgentState
from app.services import profile_service, redis_service
from app.services.research_logger import emit as emit_research_event

logger = structlog.get_logger(__name__)

# Cold (Postgres) store is durable but expensive (a commit on the cycle's critical path,
# NFR1). Redis is the per-cycle hot source; persist cold only every N affect-cycles (M1).
_COLD_PERSIST_EVERY = max(1, int(os.getenv("PROFILE_COLD_PERSIST_EVERY", "10")))


def _key(learner_id: Any) -> str:
    return f"profile:learner:{learner_id}"


async def learner_profiler_node(state: AgentState) -> dict[str, Any]:
    learner_id = state.get("learner_id")
    cycle = state.get("cycle_number")

    # Load: Redis hot -> Postgres cold/init -> default
    source = "redis"
    try:
        profile = await redis_service.get_json(_key(learner_id))
    except Exception:  # redis_service already degrades, but never let a cycle die here
        logger.warning("profile_redis_get_failed", learner_id=learner_id)
        profile = None
    if profile is None:
        db = state.get("db")
        if db is not None:
            try:
                profile = await profile_service.load_or_init(db, learner_id)
                source = "postgres_or_init"
            except Exception:
                logger.warning("profile_cold_load_failed", learner_id=learner_id)
    if profile is None:
        profile = profile_service.default_profile()
        source = "default"

    now_ms = int(time.time() * 1000)
    profile = profile_service.apply_affect(profile, state.get("affect_state"), cycle, now_ms)

    # Write-through: Redis hot (best-effort) + Postgres cold (best-effort)
    try:
        await redis_service.set_json(_key(learner_id), profile)
    except Exception:
        logger.warning("profile_redis_set_failed", learner_id=learner_id)
    db = state.get("db")
    cycle_count = int(profile.get("cycle_count", 0) or 0)
    if db is not None and cycle_count and cycle_count % _COLD_PERSIST_EVERY == 0:
        try:
            await profile_service.persist_cold(db, learner_id, profile)
        except Exception:
            logger.warning("profile_cold_persist_failed", learner_id=learner_id)

    await emit_research_event({
        "event_type": "learner_profile_updated",
        "learner_id": learner_id,
        "session_id": state.get("session_id"),
        "cycle_number": cycle or 0,
        "timestamp": now_ms,
        # Story 6.5: top-level phase/group so the event is filterable by study phase/cohort.
        "phase": state.get("phase"),
        "group": state.get("group"),
        "payload": {
            "affect_state": profile.get("affect_state"),
            "skill_level": profile.get("skill_level"),
            "affect_history_len": len(profile.get("affect_history") or []),
            "source": source,
        },
    })

    return {"learner_profile": profile, "should_adapt": should_adapt(state)}
