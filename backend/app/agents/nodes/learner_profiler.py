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

from app.agents.edges import GATE_OK, adaptation_decision
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
    profile = profile_service.apply_affect(
        profile, state.get("affect_state"), cycle, now_ms, source=state.get("affect_source")
    )

    # ---- adaptation gate ----------------------------------------------------------------
    # Evaluated HERE because this is the only point that holds the FRESH profile: the new
    # affect history is folded in above but is not yet in `state`, so evaluating the gate from
    # `state["learner_profile"]` (e.g. in the router) would silently use the PREVIOUS cycle's
    # history and the persistence rule would be off by one.
    #
    # The cooldown marker lives in the profile rather than a separate Redis key so it rides the
    # write-through below — no new I/O site. It is stamped when the gate PASSES, i.e. when an
    # adaptation is about to be attempted, not when one is confirmed delivered. If the LLM then
    # returns `no_action` the cooldown is still consumed; that errs toward fewer interventions,
    # which is the safe direction for an imperfect detector.
    # The marker is compared against `cycle_number`, which RESTARTS AT 1 each session, while
    # the profile is keyed by learner and outlives the session. A marker left by an earlier,
    # longer session therefore exceeds the current cycle and the subtraction goes negative --
    # permanently below the cooldown window, so the gate withheld `cooldown` forever. Stamping
    # the session alongside it makes a foreign marker detectable, and a foreign marker is
    # ignored rather than trusted.
    session_id = state.get("session_id")
    last_adapt = profile.get("last_adaptation_cycle")
    if profile.get("last_adaptation_session") != session_id:
        last_adapt = None
    adapt, gate_reason = adaptation_decision(state, profile, last_adapt)
    if adapt:
        profile["last_adaptation_cycle"] = int(cycle or 0)
        profile["last_adaptation_session"] = session_id

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
            # Why this cycle did or did not adapt. Makes the gate auditable from the research
            # record — the distribution of reasons is how you calibrate the thresholds.
            "adaptation_gate": gate_reason,
        },
    })

    return {
        "learner_profile": profile,
        "should_adapt": adapt,
        "adaptation_gate_reason": gate_reason,
    }
