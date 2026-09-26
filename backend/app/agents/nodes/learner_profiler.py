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

from app.agents.edges import (
    GATE_WITHHELD_RANDOM as _GATE_WITHHELD_RANDOM,
    adaptation_decision,
    arm_for,
    commit_offer,
    current_rung,
    cycles_since_offer,
    is_decisive,
    pending_offer,
    record_eligible_cycle,
    stamp_offer,
)
from app.agents import delivery_guard
from app.agents.state import AgentState
from app.services import config_service, profile_service, redis_service
from app.services.research_logger import content_coords
from app.services.research_logger import emit as emit_research_event

logger = structlog.get_logger(__name__)

# Cold (Postgres) store is durable but expensive (a commit on the cycle's critical path,
# NFR1). Redis is the per-cycle hot source; persist cold only every N affect-cycles (M1).
_COLD_PERSIST_EVERY = max(1, int(os.getenv("PROFILE_COLD_PERSIST_EVERY", "10")))


def _key(learner_id: Any) -> str:
    return f"profile:learner:{learner_id}"


def _clock_ms() -> int:
    """The server clock the cooldown is measured on. One function so the gate that reads the
    cooldown and the commit that starts it can never use different clocks (and tests can drive it).
    """
    return int(time.time() * 1000)


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

    now_ms = _clock_ms()
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
    # write-through below -- no new I/O site. It is measured on the SERVER clock
    # (`cycles_since_offer`), not by subtracting client `cycle_number` values: those restart at 1
    # whenever the lesson page remounts and differ between channels, while the session carries
    # on. The session is stamped beside the marker, so one left by an earlier session is ignored
    # rather than trusted.
    session_id = state.get("session_id")
    affect_source = state.get("affect_source")
    # A SYNCHRONOUS cache read, not a database call: the cache is primed at startup and
    # invalidated on write, so a threshold changed on the settings page applies from the next
    # cycle without putting a query in the hot path.
    config = config_service.get_config()
    adapt, gate_reason = adaptation_decision(
        state, profile, None, config,
        cycles_since_last_offer=cycles_since_offer(profile, session_id, now_ms),
    )
    # Read BEFORE advancing: this is the rung the strategist should use for THIS cycle, and the
    # stored counter is how many were delivered BEFORE it. Reading after would open every learner
    # one rung deep and the first rung of every ladder would never be used.
    section_id = (state.get("content_context") or {}).get("section_id")
    rung = current_rung(profile, session_id, section_id, state.get("affect_state"))
    # A card the learner dismissed was "not now", not "that did not help": it does not count as a
    # rung tried, so the next offer here is the same rung rather than a heavier one.
    rung = max(0, rung - delivery_guard.rung_credit(
        state.get("ui_state"), section_id, state.get("affect_state")
    ))

    # WHAT THIS CYCLE SPENDS, AND WHEN.
    #
    # A cycle withheld by the trial draw is complete here: it cleared every gate condition and
    # must spend the cooldown and the session cap exactly as a delivered one does, otherwise the
    # control arm becomes eligible again sooner and stops being matched to the delivered arm. It
    # does not advance the ladder -- it showed the learner nothing, so nothing was tried.
    #
    # A cycle that PASSED has not shown the learner anything yet. The strategist may still choose
    # `no_action`, the adapter may drop text identical to earlier help, the socket handler may drop
    # a card for a section the learner has left, or the send may fail. Stamping here spent the
    # cooldown, the cap and a ladder rung on cards the learner never saw, so the ladder could climb
    # (or reach `ladder_exhausted`) on help that was never shown. The cost is therefore carried
    # forward as `offer_commit` and spent by the socket handler only after a successful send
    # (`commit_delivered_offer`). A learner request is carried the same way: it advances the
    # ladder when its card arrives, and never spends the cooldown or the cap, which pace the
    # DETECTOR and are not a budget on help the learner asked for.
    if gate_reason == _GATE_WITHHELD_RANDOM:
        stamp_offer(profile, session_id, now_ms)
        record_eligible_cycle(profile, session_id)
    offer = pending_offer(state, gate_reason)

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
        # Migration 021: where in the course this happened. Read from the same section context
        # the prompt is grounded in, so the decision and the content it was about stay joined.
        **content_coords(state.get("content_context")),
        "payload": {
            "affect_state": profile.get("affect_state"),
            "skill_level": profile.get("skill_level"),
            "affect_history_len": len(profile.get("affect_history") or []),
            # NOTE: the PROFILE STORE this cycle read from (redis / postgres_or_init / default).
            # It is not affect provenance -- see `affect_source` below, which is.
            "source": source,
            # Why this cycle did or did not adapt. Makes the gate auditable from the research
            # record — the distribution of reasons is how you calibrate the thresholds.
            "adaptation_gate": gate_reason,
            # WHICH CHANNEL the gate ruled on, and the floor it was held to.
            #
            # Both modalities run the whole graph inside one cycle_number, so a cycle produces two
            # of these events. Without provenance the durable record could not say which channel a
            # `low_confidence` verdict belonged to -- and the two channels have different floors
            # (geometry 0.70 against a 0.50 global), so the verdict was uninterpretable after the
            # fact. `is_decisive` is stamped too: a channel can clear every threshold and still be
            # withheld for having no authority, and that is not visible from the reason alone.
            "affect_source": affect_source,
            "affect_confidence": state.get("affect_confidence"),
            "min_confidence_applied": config.min_confidence_for(affect_source),
            "decisive_channel": is_decisive(affect_source, config.decisive_sources),
            # RANDOMISED TRIAL ARM: "delivered", "withheld", or None when the cycle never became
            # eligible and so belongs to neither. Analysis must filter to the two named arms --
            # a null here is not a control observation, it is a cycle that never qualified.
            "arm": arm_for(gate_reason),
            # Read from the LIVE config, not from a module constant imported by value. The
            # constant was bound at this module's import time, so once the rate became editable
            # it would have kept stamping the value the process started with -- the record would
            # have reported a trial condition that was no longer in force, and nothing downstream
            # could have detected it.
            "withhold_rate": config.withhold_rate,
            # Which configuration produced this decision, so an analysis can split on a change.
            "config_version": config.version,
        },
    })

    return {
        "learner_profile": profile,
        "should_adapt": adapt,
        "adaptation_gate_reason": gate_reason,
        "ladder_rung": rung,
        "offer_commit": offer,
    }


async def commit_delivered_offer(
    learner_id: Any, offer: dict | None, db: Any = None, now_ms: int | None = None
) -> bool:
    """Spend what a card cost, once it has actually reached the learner. Never raises.

    Called by the socket handler after a successful send, with the `offer_commit` the profiler
    carried forward. Reads the profile the profiler wrote this cycle, applies `commit_offer`
    (cooldown and cap for a detector-driven card, a ladder rung for both kinds), and writes it
    back. When Redis is unavailable the profile came from Postgres, so it is persisted there
    instead -- otherwise the cooldown would be lost and the next cycle could offer again at once.
    """
    if not offer:
        return False
    stamp_ms = int(now_ms if now_ms is not None else _clock_ms())
    try:
        profile = await redis_service.get_json(_key(learner_id))
        from_cold = False
        if profile is None and db is not None:
            profile = await profile_service.load_or_init(db, learner_id)
            from_cold = True
        if profile is None:
            logger.warning("offer_commit_no_profile", learner_id=learner_id)
            return False
        if not commit_offer(profile, offer, stamp_ms):
            return False
        await redis_service.set_json(_key(learner_id), profile)
        if from_cold:
            await profile_service.persist_cold(db, learner_id, profile)
        return True
    except Exception:
        logger.warning("offer_commit_failed", learner_id=learner_id, exc_info=True)
        return False
