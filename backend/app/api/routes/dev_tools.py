"""Dev-only harness for the adaptation loop.

WHY THIS EXISTS

The adaptation loop is the platform's central claim, and it is close to untestable through the
product. To see a `show_breakdown` a learner must be genuinely confused, for two consecutive
cycles ON THE SAME CHANNEL, above a 0.70 floor, on a channel authorised to decide, outside a
cooldown, not drawn into the withheld arm, and already one rung deep in that section. Sitting in
front of a webcam trying to produce that is not a test strategy, and the consequence showed: a
live pilot session produced thirteen cycles, three interventions, and every one of them was
`skip_ahead`. Five of the eight action types had never been seen by anyone.

This forces one cycle on demand and reports what the real machinery did with it.

WHAT IT DOES NOT DO

  * It does not weaken the gate. Full-loop mode runs the compiled graph and the live gate config,
    so `frustrated` returns `state_not_actionable` on a deployment whose `ADAPT_STATES` omits it.
    That verdict is a finding, and the response says so rather than arranging for it not to happen.
  * It does not leave the learner's profile seeded. The gate reads the profile for its persistence
    and ladder conditions, so a run has to write one; it is snapshotted first and put back in a
    `finally`. `purge_synthetic_events.py` documents what happens otherwise -- seventeen stale
    `bored` entries left the sustain condition satisfiable by a single genuine detection landing
    on top of them.
  * It does not fabricate a help history. Forced-action mode writes no research event and no
    assistance ledger row, so nothing it pushes can turn up in the learner's `/progress` help
    history as though it had been earned.

Everything full-loop mode emits is stamped `synthetic: true` inside the event payload by
`research_logger.synthetic_run`, on a synthetic session id, so both the sessions and the rows are
identifiable without anyone having written a list down.

PRODUCTION: every route here 404s when `ENVIRONMENT` is production, before any argument is read.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import edges
from app.agents.graph import get_graph
from app.agents.nodes.terminal import deliver_node
from app.agents.state import make_initial_state
from app.api.routes.ws import _deliver_adaptation
from app.core.config import settings
from app.core.deps import get_db, require_role
from app.models.user import Role, User
from app.schemas.dev_tools import SimulateCycleRequest, SimulateCycleResponse
from app.services import (
    config_service,
    content_context_service,
    profile_service,
    redis_service,
    research_logger,
)
from app.services.connection_manager import connection_manager
from app.services.research_logger import content_coords

logger = structlog.get_logger(__name__)
router = APIRouter()

#: Highest cycle number the arm search will consider. The draw is a hash, so a qualifying cycle
#: turns up within a handful of tries for any rate that is not 0 or 1; the bound exists so an
#: unreachable arm fails fast instead of spinning.
_ARM_SEARCH_LIMIT = 200


def _assert_dev() -> None:
    """404 outside development, before anything else runs.

    This endpoint fabricates affect readings, writes to the research record, and pushes messages
    to a learner's screen. In production none of those should be reachable by anyone at all, so
    the check is on the environment and there is no flag that turns it back on.
    """
    if settings.ENVIRONMENT.lower() == "production":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Not found"}},
        )


def _pick_cycle(learner_id: str, session_id: str, rate: float, arm: str) -> tuple[int, list[str]]:
    """Choose a cycle number that lands in the requested trial arm.

    `edges.withhold_draw` is a SHA-256 of `(learner, session, cycle)` rather than a PRNG draw --
    it exists that way so a historical arm can be re-derived from the record months later -- which
    also means the arm of a cycle is knowable before running it. Picking the cycle is therefore
    the honest way to reach a given arm: the gate is untouched and the real draw still decides.

    Returns the cycle and any notes about an arm that could not be reached.
    """
    notes: list[str] = []
    if arm == "any":
        return 1, notes

    want_withheld = arm == "withheld"
    for cycle in range(1, _ARM_SEARCH_LIMIT):
        withheld = rate > 0.0 and edges.withhold_draw(learner_id, session_id, cycle) < rate
        if withheld == want_withheld:
            return cycle, notes

    notes.append(
        f"No cycle in the first {_ARM_SEARCH_LIMIT} lands in the '{arm}' arm at a withhold rate "
        f"of {rate}. Ran cycle 1 instead; check the reported gate reason for the arm it fell in."
    )
    return 1, notes


def _seed_profile(
    body: SimulateCycleRequest, session_id: str, section_id: Any, config: Any
) -> tuple[dict[str, Any], list[str]]:
    """Build the profile the gate needs to see for this cycle to be the one being tested.

    Three of the gate's conditions read the profile rather than the cycle, so none of them can be
    exercised from a single fabricated reading alone:

      * PERSISTENCE. `sustain_history` reads `affect_history_by_source[source]`, not the
        interleaved list -- the graph runs once per modality, so the interleaved history's last
        two entries are usually two channels disagreeing inside one cycle. Seeding the wrong one
        produces `not_sustained` and looks like a broken harness.
      * THE LADDER. `current_rung` is what decides `show_hint` against `show_breakdown` against
        `show_alternative`, and it is scoped to `(session, section, state)`. Advancing it through
        `record_delivered_rung` rather than writing the key by hand keeps it impossible for the
        two to disagree about the key's shape.
      * THE SESSION CAP, which counts eligible cycles within one session id.

    Returns the profile and any notes about a setting that makes this run pointless before it is
    run. `_seeded_profile` below owns installing and removing it.
    """
    notes: list[str] = []
    profile = profile_service.default_profile()

    need = max(1, config.min_consecutive)
    history = [body.affect_state] * need
    profile["affect_history"] = list(history)
    profile["affect_history_by_source"] = {body.affect_source: list(history)}
    profile["affect_state"] = body.affect_state

    for _ in range(body.rung):
        edges.record_delivered_rung(profile, session_id, section_id, body.affect_state)
    # `record_delivered_rung` claims the session for the profile, which is also what the cap is
    # counted against. Zeroed explicitly so a rung > 0 never reads as a session already spent.
    if body.rung:
        profile["eligible_this_session"] = 0

    if config.max_per_session <= 0:
        notes.append(
            "max_per_session is 0, so every eligible cycle returns 'session_cap'. "
            "Raise it on the admin settings page to see anything delivered."
        )
    return profile, notes


@asynccontextmanager
async def _seeded_profile(db: AsyncSession, user_id: str, profile: dict[str, Any]):
    """Install `profile` for the duration of the block, then put the learner's own back.

    BOTH STORES, because the profiler reads Redis first and falls through to Postgres. Seeding
    only the hot copy works right up until Redis is down, at which point the run silently judges
    the cycle against the learner's real history and reports `not_sustained` with nothing to say
    why. Seeding only the cold copy loses to a stale hot one for the same reason in reverse.

    RESTORED IN A `finally`, because what is being installed is fabricated affect history. Left
    behind, it makes the gate's sustain condition satisfiable by a single genuine detection landing
    on top of `min_consecutive` invented ones -- an intervention no real evidence supports, and
    exactly the damage `purge_synthetic_events.py` was written to repair.

    An absent profile is restored as ABSENT (the cold row is deleted, the hot copy reset), not as
    a default one: a learner who has never been seen must not come out of this looking like one
    who has.
    """
    key = f"profile:learner:{user_id}"
    hot_before = await redis_service.get_json(key)
    cold_before = await profile_service.load_cold(db, user_id)
    try:
        await redis_service.set_json(key, profile)
        await profile_service.persist_cold(db, user_id, profile)
        yield
    finally:
        await redis_service.set_json(
            key, hot_before if hot_before is not None else profile_service.default_profile()
        )
        if cold_before is not None:
            await profile_service.persist_cold(db, user_id, cold_before)
        else:
            await profile_service.delete_cold(db, user_id)


def _reachability_notes(body: SimulateCycleRequest, config: Any) -> list[str]:
    """Say plainly which of the requested conditions cannot occur on this deployment.

    A green run against a forced condition is otherwise indistinguishable from a working
    capability, and three of the eight actions are unreachable here by configuration rather than
    by accident.
    """
    notes: list[str] = []
    if body.affect_state not in config.adapt_states:
        notes.append(
            f"'{body.affect_state}' is not in ADAPT_STATES ({', '.join(config.adapt_states)}), so "
            f"the gate will return 'state_not_actionable'. Its whole ladder -- for 'frustrated' "
            f"that is show_encouragement, simplify and suggest_break -- cannot occur organically "
            f"on this deployment at any confidence."
        )
    if not edges.is_decisive(body.affect_source, config.decisive_sources):
        notes.append(
            f"'{body.affect_source}' is not a decisive channel "
            f"({', '.join(config.decisive_sources)}), so it is logged but may not intervene "
            f"alone. Expect 'channel_advisory'."
        )
    floor = config.min_confidence_for(body.affect_source)
    if body.affect_confidence < floor:
        notes.append(
            f"Confidence {body.affect_confidence} is below this channel's floor of {floor}."
        )
    return notes


def _gate_config_view(config: Any) -> dict[str, Any]:
    """The settings this cycle was judged against, so a verdict is explicable from the response."""
    return {
        "version": config.version,
        "adaptStates": list(config.adapt_states),
        "decisiveSources": list(config.decisive_sources),
        "minConsecutive": config.min_consecutive,
        "cooldownCycles": config.cooldown_cycles,
        "withholdRate": config.withhold_rate,
        "maxPerSession": config.max_per_session,
    }


@router.post("/simulate-cycle", response_model=SimulateCycleResponse)
async def simulate_cycle(
    body: SimulateCycleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.learner)),
) -> SimulateCycleResponse:
    """Run one fabricated cycle for the CALLING learner and report what happened.

    The learner is always `current_user` -- it is not a parameter -- so this cannot push a card to
    anyone else's screen or seed anyone else's profile.
    """
    _assert_dev()

    content_context = await content_context_service.build(body.section_id, db)
    if not content_context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Unknown section"}},
        )

    user_id = str(current_user.id)
    # A distinct, self-identifying session id. Every event this run emits is filed under it, so
    # the run is separable from the learner's real sessions by id as well as by the payload mark.
    session_id = f"devsim-{uuid.uuid4().hex[:12]}"

    if body.action_type:
        return await _forced_action(body, user_id, session_id)
    return await _full_loop(body, user_id, session_id, content_context, db)


async def _forced_action(
    body: SimulateCycleRequest, user_id: str, session_id: str
) -> SimulateCycleResponse:
    """Build one action's wire message directly and push it. No gate, no strategist, no model.

    For checking that a card renders and that the socket carries it. Deliberately writes NOTHING
    durable: no research event and no assistance ledger row, so a forced push can never surface in
    the learner's help history or in the dataset as an intervention that was decided upon.
    """
    action = body.action_type
    text = body.text or (
        f"Synthetic '{action}' from the adaptation harness. No model produced this text."
    )
    update = await deliver_node({  # type: ignore[arg-type]
        "adaptation_content": {
            "text": text,
            "variant": action,
            "metadata": {"action_type": action, "generated": False, "fallback": True},
        }
    })
    message = update.get("delivery_message")

    notes = [
        (
            "Forced action: the gate and the strategist were both skipped, so this says nothing "
            "about whether the loop would have chosen it."
        ),
        "Nothing durable was written -- no research event, no assistance ledger row.",
    ]
    if message is None:
        notes.append(
            f"'{action}' is not a deliverable action (deliver_node builds no message for it), "
            f"so nothing was sent."
        )
        return SimulateCycleResponse(
            mode="forced_action", session_id=session_id, cycle_number=0,
            action_type=action, notes=notes,
        )

    sent = await connection_manager.send_to(user_id, message)
    if not sent:
        notes.append("No live WebSocket for this learner, so nothing reached a screen.")

    return SimulateCycleResponse(
        mode="forced_action",
        session_id=session_id,
        cycle_number=0,
        action_type=action,
        adaptation_id=message.get("adaptation_id"),
        text=text,
        variant=action,
        generated=False,
        delivered=sent,
        notes=notes,
    )


async def _full_loop(
    body: SimulateCycleRequest,
    user_id: str,
    session_id: str,
    content_context: dict[str, Any],
    db: AsyncSession,
) -> SimulateCycleResponse:
    """Run the compiled graph end to end with a fabricated affect reading.

    The affect is pre-seeded into the state rather than injected into `affect_detection_node`: with
    no payload that node reports an empty cycle and returns no affect keys, so LangGraph's merge
    leaves the seeded values in place. The detection node keeps its production behaviour and knows
    nothing about this path -- which matters, because it is the node the thesis reports on.

    Everything downstream is the real thing: the real profiler, the real gate against the live
    config, the real strategist, the real content adapter, the real delivery.
    """
    config = config_service.get_config()
    section_id = content_context.get("section_id")

    cycle, notes = _pick_cycle(user_id, session_id, config.withhold_rate, body.arm)
    notes += _reachability_notes(body, config)

    profile, seed_notes = _seed_profile(body, session_id, section_id, config)
    notes += seed_notes

    state = make_initial_state(
        learner_id=user_id,
        session_id=session_id,
        cycle_number=cycle,
        db=db,
        content_context=content_context,
        # Forced, because the gate's eligibility check is phase/group and a real learner in the
        # control arm would never reach the strategist at all.
        phase="phase_b",
        group="adaptive",
    )
    state["affect_state"] = body.affect_state
    state["affect_confidence"] = body.affect_confidence
    state["affect_source"] = body.affect_source

    had_socket = connection_manager.is_connected(user_id)
    async with _seeded_profile(db, user_id, profile):
        with research_logger.synthetic_run():
            result = await get_graph().ainvoke(state)
            await _deliver_adaptation(
                result, user_id, session_id, cycle,
                phase="phase_b", group="adaptive",
                coords=content_coords(content_context), db=db,
            )

    message = result.get("delivery_message") or {}
    content = result.get("adaptation_content") or {}
    metadata = content.get("metadata") or {}
    strategy = result.get("strategy") or {}
    gate_reason = result.get("adaptation_gate_reason")

    if not message:
        notes.append(
            f"Nothing was delivered. Gate said '{gate_reason}'"
            + (f", strategist chose '{strategy.get('action_type')}'." if strategy else ".")
        )
    elif not had_socket:
        notes.append(
            "An adaptation was produced but there was no live WebSocket, so nothing reached a "
            "screen. It is recorded as a failed delivery, which is what a real one would be."
        )
    if metadata.get("fallback"):
        notes.append(
            "The text came from the rule fallback, not the language model"
            + (f" ({metadata.get('fallback_reason')})." if metadata.get("fallback_reason") else ".")
        )

    logger.info(
        "dev_simulate_cycle",
        learner_id=user_id, session_id=session_id, cycle=cycle,
        affect_state=body.affect_state, rung=body.rung,
        gate_reason=gate_reason, action=message.get("action"),
    )

    return SimulateCycleResponse(
        mode="full_loop",
        session_id=session_id,
        cycle_number=cycle,
        gate_reason=gate_reason,
        should_adapt=bool(result.get("should_adapt")),
        ladder_rung=result.get("ladder_rung"),
        action_type=message.get("action") or strategy.get("action_type"),
        adaptation_id=message.get("adaptation_id"),
        text=(message.get("content") or {}).get("text"),
        variant=(message.get("content") or {}).get("variant"),
        generated=bool(metadata.get("generated")) if metadata else None,
        fallback=bool(metadata.get("fallback")) if metadata else None,
        fallback_reason=metadata.get("fallback_reason"),
        delivered=bool(message) and had_socket,
        notes=notes,
        gate_config=_gate_config_view(config),
    )
