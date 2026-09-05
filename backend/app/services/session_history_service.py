"""One learner session, reconstructed from the research record and indexed by cycle.

WHY THIS EXISTS

The Monitor's live view is served by an SSE stream whose backlog is 200 events out of a 500-slot
IN-PROCESS ring buffer -- roughly seven to ten cycles, and gone entirely on restart. Every question
worth asking of a finished session ("when did the state change", "how long was the learner
confused", "why did the gate withhold on cycle 14") is therefore unanswerable from the stream.
`research_events` has all of it; nothing joined it up.

WHAT THE JOIN IS, AND WHY IT BELONGS HERE

Both modalities run the whole agent graph independently within a single `cycle_number`, so one cycle
produces a facial detection, a behavioural detection, one `learner_profile_updated` per modality,
and -- when the gate opens -- a strategy, a generation and a delivery. Presenting that as a flat
event list asks the reader to do the join in their head, and the derived quantities (state changes,
time in state) would then be computed in the browser, where they could silently disagree with the
CSV export. Doing it once, server-side, means the UI and the export describe the same session.

WHAT THIS DELIBERATELY DOES NOT DO

It does not invent the parts of the chain the backend never wrote down. In particular the hint TEXT,
the strategist's rationale, per-node timings and a hint-to-response link do not exist in the record
(see `docs/` and the field audit); `missing` names them per cycle so the UI can say "not recorded"
with a reason instead of rendering an empty box that reads as "nothing happened".
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_event import ResearchEvent

logger = structlog.get_logger(__name__)

FACIAL = "facial_affect_detected"
BEHAVIORAL = "behavioral_affect_detected"
MULTIMODAL = "multimodal_affect_detected"
PROFILE = "learner_profile_updated"
STRATEGY = "strategy_decided"
TRIGGERED = "adaptation_triggered"
DELIVERED = "adaptation_delivered"
INTERACTION = "adaptation_interaction"
SELF_REPORT = "self_report"
DELIVERY_FAILED = "adaptation_delivery_failed"
CONNECTED = "ws_connected"
RECONNECTED = "ws_reconnected"
DISCONNECTED = "ws_disconnected"

#: Detection events, in the order a cycle's "final" state is taken from. Fusion wins when present
#: because it is the combined reading; otherwise whichever channel reported.
_DETECTION_ORDER = (MULTIMODAL, FACIAL, BEHAVIORAL)

#: States that are an affect DETECTION rather than the absence of one. `engaged` is the negative
#: class of both binary heads -- "no confusion found" / "no disengagement found" -- so a run of
#: `engaged` is not evidence of engagement and is labelled as such downstream.
_NEGATIVE_CLASS = "engaged"


def _payload(row: ResearchEvent) -> dict[str, Any]:
    p = row.payload
    return p if isinstance(p, dict) else {}


def _sort_key(row: ResearchEvent) -> tuple[int, int]:
    """Order within a session. `sequence_number` is monotonic per session and is the authority;
    `timestamp` breaks ties for rows written before sequencing, and for client-sourced events."""
    return (int(row.timestamp or 0), int(row.sequence_number or 0))


def _cycle_state(cycle: dict[str, Any]) -> tuple[str | None, float | None, str | None]:
    """The state this cycle resolved to, its confidence, and which channel it came from."""
    for key, kind in (("fused", MULTIMODAL), ("facial", FACIAL), ("behavioural", BEHAVIORAL)):
        p = cycle.get(key)
        if p and p.get("affect_state"):
            return p["affect_state"], p.get("affect_confidence"), p.get("affect_source")
    return None, None, None


def _state_changes(cycles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transitions between consecutive resolved states, with how long the previous one held.

    Derived, not recorded: the system stores a state per cycle and never a duration, so "confused
    for 18 seconds" is arithmetic over consecutive cycles. Keeping that arithmetic here rather than
    in the browser is what stops the timeline and the CSV export from disagreeing.

    A cycle that resolved to NO state (empty cycle, learner absent, inference error) closes the
    current run rather than extending it. Treating a gap as a continuation would report a learner
    as confused throughout a period in which nothing was observed -- and an absent learner is
    exactly when that misreading matters most.

    `durationMs` is null on the final run: the session may still be open, and the alternative is to
    invent an end time.
    """
    changes: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def close(at: int | None) -> None:
        if current is not None and at is not None and current.get("at") is not None:
            current["durationMs"] = max(0, int(at) - int(current["at"]))

    for c in cycles:
        state, conf, source = _cycle_state(c)
        at = c.get("started_at")

        if state is None:
            # Observation gap: close the run at the point observation stopped.
            close(at)
            current = None
            continue

        if current is None or state != current["to"]:
            close(at)
            current = {
                "at": at,
                "cycle_number": c.get("cycle_number"),
                "from": current["to"] if current else None,
                "to": state,
                "confidence": conf,
                "source": source,
                "durationMs": None,
                # How many consecutive cycles this run has covered so far. The gate's persistence
                # rule counts cycles, not seconds, so this is the quantity it actually acts on.
                "cycles": 1,
            }
            changes.append(current)
        else:
            current["cycles"] = int(current.get("cycles", 1)) + 1

    return changes


def _summary(session_id: str, cycles: list[dict[str, Any]], changes: list[dict[str, Any]],
             rows: list[ResearchEvent]) -> dict[str, Any]:
    times = [int(r.timestamp or 0) for r in rows if r.timestamp]
    started = min(times) if times else None
    ended = max(times) if times else None

    confs = [c for c in (_cycle_state(x)[1] for x in cycles) if isinstance(c, (int, float))]
    by_state: dict[str, int] = {}
    for x in cycles:
        s = _cycle_state(x)[0]
        if s:
            by_state[s] = by_state.get(s, 0) + 1

    # Time spent in each state, from the transition durations. The final run has no duration
    # because the session may still be open -- it is reported separately rather than guessed.
    dwell: dict[str, int] = {}
    for ch in changes:
        if ch.get("durationMs") and ch.get("to"):
            dwell[ch["to"]] = dwell.get(ch["to"], 0) + int(ch["durationMs"])

    delivered = sum(1 for r in rows if r.event_type == DELIVERED)
    triggered = sum(1 for r in rows if r.event_type == TRIGGERED)

    return {
        "sessionId": session_id,
        "startedAt": started,
        "endedAt": ended,
        "durationMs": (ended - started) if (started and ended) else None,
        "cycleCount": len(cycles),
        "detectionCount": sum(1 for c in cycles if _cycle_state(c)[0] is not None),
        "stateChangeCount": len(changes),
        "interventionsTriggered": triggered,
        "interventionsDelivered": delivered,
        # A triggered adaptation with no matching delivery is the ONLY signal that delivery failed:
        # the failure path logs at debug and emits no event.
        "deliveriesUnaccounted": max(0, triggered - delivered),
        "meanConfidence": round(sum(confs) / len(confs), 4) if confs else None,
        "byState": by_state,
        "dwellMsByState": dwell,
        "selfReports": sum(1 for r in rows if r.event_type == SELF_REPORT),
    }


async def session_history(db: AsyncSession, session_id: str) -> dict[str, Any]:
    """Everything the record holds about one session, indexed by cycle."""
    stmt = select(ResearchEvent).where(ResearchEvent.session_id == session_id)
    rows = sorted((await db.execute(stmt)).scalars().all(), key=_sort_key)

    if not rows:
        return {"sessionId": session_id, "found": False, "cycles": [],
                "stateChanges": [], "interventions": [], "summary": None}

    by_cycle: dict[int, dict[str, Any]] = {}

    def cycle(n: int) -> dict[str, Any]:
        return by_cycle.setdefault(int(n), {
            "cycle_number": int(n), "started_at": None,
            "facial": None, "behavioural": None, "fused": None,
            "gate": None, "strategy": None, "triggered": None, "delivered": None,
            "delivery_failed": None, "response": None,
        })

    interventions: list[dict[str, Any]] = []
    interactions: list[dict[str, Any]] = []
    self_reports: list[dict[str, Any]] = []

    for r in rows:
        p = _payload(r)
        n = int(r.cycle_number or 0)
        t = int(r.timestamp or 0)

        if r.event_type in (FACIAL, BEHAVIORAL, MULTIMODAL):
            c = cycle(n)
            key = {FACIAL: "facial", BEHAVIORAL: "behavioural", MULTIMODAL: "fused"}[r.event_type]
            c[key] = {**p, "timestamp": t}
            c["started_at"] = min(c["started_at"], t) if c["started_at"] else t
        elif r.event_type == PROFILE:
            c = cycle(n)
            # Two profile events per cycle (one per modality) and the durable row carries no
            # affect_source, so the LAST one wins here. `affect_source` is added to this payload
            # going forward; older rows simply cannot be attributed to a channel.
            c["gate"] = {"reason": p.get("adaptation_gate"), "affect_state": p.get("affect_state"),
                         "affect_source": p.get("affect_source"), "timestamp": t}
        elif r.event_type == STRATEGY:
            cycle(n)["strategy"] = {**p, "timestamp": t}
        elif r.event_type == TRIGGERED:
            cycle(n)["triggered"] = {**p, "timestamp": t}
        elif r.event_type == DELIVERED:
            cycle(n)["delivered"] = {**p, "timestamp": t}
        elif r.event_type == DELIVERY_FAILED:
            # The gate opened and the learner received nothing. Distinct from "never generated".
            cycle(n)["delivery_failed"] = {**p, "timestamp": t}
        elif r.event_type == INTERACTION:
            # cycle_number is 0 on this event (the client never sets it), so it cannot be joined
            # to the hint it responded to. Kept as a session-level list rather than forced into a
            # cycle it may not belong to.
            interactions.append({**p, "timestamp": t})
        elif r.event_type == SELF_REPORT:
            self_reports.append({**p, "timestamp": t})

    cycles = [by_cycle[k] for k in sorted(by_cycle)]

    # A learner response joins its hint by the SERVER-issued adaptation_id. Before that id existed
    # the client minted its own, so `adaptation_interaction` referenced something the backend had
    # never seen and no join was possible at all; responses recorded under a client id therefore
    # stay in the session-level list rather than being attached to a guess.
    delivered_by_id = {
        (c["delivered"] or {}).get("adaptation_id"): c
        for c in cycles
        if (c.get("delivered") or {}).get("adaptation_id")
    }
    for it in interactions:
        target = delivered_by_id.get(it.get("adaptation_id"))
        if target is not None:
            target["response"] = it

    changes = _state_changes(cycles)

    for c in cycles:
        if c.get("strategy") or c.get("triggered") or c.get("delivered") or c.get("delivery_failed"):
            state, conf, source = _cycle_state(c)
            interventions.append({
                "cycle_number": c["cycle_number"],
                "detection": {"state": state, "confidence": conf, "source": source},
                "gate": c.get("gate"),
                "strategy": c.get("strategy"),
                "triggered": c.get("triggered"),
                "delivered": c.get("delivered"),
                "deliveryFailed": c.get("delivery_failed"),
                "response": c.get("response"),
                # The state the NEXT cycle resolved to. Sequence, not causation: nothing in the
                # record links a hint to a subsequent state, and presenting it as an outcome would
                # assert a relationship the data cannot support.
                "nextState": _next_state_after(cycles, c["cycle_number"]),
                # Named so the UI can render "not recorded" with a reason rather than a blank.
                "missing": _missing_for(c),
            })

    return {
        "sessionId": session_id,
        "found": True,
        "cycles": cycles,
        "stateChanges": changes,
        "interventions": interventions,
        "interactions": interactions,
        "selfReports": self_reports,
        "summary": _summary(session_id, cycles, changes, rows),
    }


def _next_state_after(cycles: list[dict[str, Any]], n: int) -> dict[str, Any] | None:
    """The state the next cycle that detected anything resolved to.

    Deliberately NOT called an outcome. No recorded relationship links an intervention to a later
    state -- self-reports are triggered by section completion, not by delivery, and carry no
    reference to one -- so this is the next reading in time and nothing more. Labelling it an
    effect would assert causation the record cannot support.
    """
    for c in cycles:
        if int(c.get("cycle_number") or 0) <= n:
            continue
        state, conf, source = _cycle_state(c)
        if state:
            return {"cycle_number": c["cycle_number"], "state": state,
                    "confidence": conf, "source": source, "at": c.get("started_at")}
    return None


def _missing_for(cycle: dict[str, Any]) -> list[str]:
    """Which parts of this cycle's chain the backend does not record.

    Returned per cycle so the UI states the gap rather than implying the step did not happen. These
    are properties of the instrumentation, not of the session.
    """
    gaps: list[str] = []
    trig = cycle.get("triggered") or {}
    strat = cycle.get("strategy") or {}
    # `text` and `reason` are recorded from the change that added them onward. Their absence on an
    # older row is a property of when it was written, not of what happened, and the UI says so.
    if trig and not trig.get("text"):
        gaps.append("hint_text")
    if strat and not strat.get("reason"):
        gaps.append("strategy_reason")
    if trig and not cycle.get("delivered") and not cycle.get("delivery_failed"):
        gaps.append("delivery_unconfirmed")
    if cycle.get("delivered") and not cycle.get("response"):
        # Only skip_ahead, increase_difficulty and (now) hint dismissal report at all; silence is
        # not evidence the learner ignored it.
        gaps.append("no_response_recorded")
    return gaps
