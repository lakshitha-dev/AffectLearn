"""Replay recorded cycles through the adaptation gate at settings other than the deployed ones.

WHAT QUESTION THIS ANSWERS

The gate's thresholds were calibrated on out-of-fold predictions from DUX -- a corpus of business
software users completing travel-expense forms. Section 7.4 records the two artefacts that
inherits: the task is not a learning task, and the simulation treats adjacent surviving windows
as consecutive where the live pipeline does not discard windows. It also records the fix: "the
deployed system now records a reason whenever it withholds an intervention, so the calibration
can be repeated on real cycles once the pilot supplies them."

This is that repeat. It walks the recorded readings for each session in cycle order and asks what
WOULD have happened at a different confidence floor, a different sustain requirement, a different
cooldown, or with a different set of channels authorised to decide.

WHY IT IS A PARAMETERISED TWIN RATHER THAN THE GATE ITSELF

`passes_adaptation_gate` reads module-level constants. Replaying at other settings would mean
mutating those globals, which changes live behaviour for every concurrent request in the process
and is not something a read-only analysis endpoint should be able to do.

So the logic is restated here with every threshold as an argument -- and
`test_replay_matches_the_real_gate` asserts the two agree across the decision space at the
deployed configuration. If the real gate changes and this does not, that test fails. A replay
that had silently drifted from the gate would be worse than no replay, because its output would
still look like evidence.

WHAT IT CANNOT TELL YOU

It replays the RECORD, so it can only reason about readings that were actually taken. Raising a
floor can only ever remove interventions from what was recorded; lowering one can only add
interventions among cycles that already produced a reading. It cannot invent a cycle the
detector never scored, and it cannot tell you what a learner would have done differently.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.edges import (
    GATE_CHANNEL_ADVISORY,
    GATE_COOLDOWN,
    GATE_LOW_CONFIDENCE,
    GATE_NO_AFFECT,
    GATE_NOT_SUSTAINED,
    GATE_OK,
    GATE_STATE_NOT_ACTIONABLE,
)
from app.models.research_event import ResearchEvent
from app.services import config_service

logger = structlog.get_logger(__name__)

#: Events carrying an affect reading the gate could have acted on.
DETECTION_EVENTS = (
    "facial_affect_detected",
    "behavioral_affect_detected",
    "multimodal_affect_detected",
    "performance_signal_detected",
)

SELF_REPORT_EVENT = "self_report"

#: Self-reported states that make an intervention WARRANTED. `engaged` and `neutral` do not: a
#: learner who reports either was not in need of help, whatever the detector thought.
NEGATIVE_SELF_REPORTS = frozenset({"confused", "bored", "frustrated"})

#: How many cycles either side of an intervention a self-report may sit and still be treated as
#: describing the same moment. Self-reports arrive at section boundaries rather than on the cycle
#: clock, so an exact match would find almost nothing; two cycles is about a minute.
SELF_REPORT_WINDOW_CYCLES = 2

#: Below this many matched self-reports, precision is reported as None. The deployed figure of
#: 0.500 rests on nine warranted offers in eighteen with an interval spanning [0.273, 0.737];
#: reporting a ratio over three or four would be worse than reporting nothing.
MIN_PRECISION_SAMPLE = 10


def replay_gate(
    *,
    affect_state: str | None,
    affect_confidence: float | None,
    affect_history: Sequence[str],
    cycle_number: int | None,
    last_adaptation_cycle: int | None,
    affect_source: str | None,
    min_confidence: float,
    min_consecutive: int,
    cooldown_cycles: int,
    decisive_sources: Sequence[str],
    adapt_states: Sequence[str],
) -> tuple[bool, str]:
    """The gate's decision, with every threshold supplied rather than read from the environment.

    Mirrors `passes_adaptation_gate` exactly, INCLUDING the order of the checks. The order is not
    cosmetic: authority is evaluated last so that `channel_advisory` appears only on cycles that
    would otherwise have intervened, which is what makes counting them a measurement of what an
    advisory channel would have done rather than a count of everything it ever saw.
    """
    if not affect_state:
        return False, GATE_NO_AFFECT

    if affect_state not in adapt_states:
        return False, GATE_STATE_NOT_ACTIONABLE

    if float(affect_confidence or 0.0) < min_confidence:
        return False, GATE_LOW_CONFIDENCE

    need = max(1, min_consecutive)
    recent = list(affect_history)[-need:]
    if len(recent) < need or any(a != affect_state for a in recent):
        return False, GATE_NOT_SUSTAINED

    if last_adaptation_cycle is not None and cycle_number is not None:
        if int(cycle_number) - int(last_adaptation_cycle) < cooldown_cycles:
            return False, GATE_COOLDOWN

    if decisive_sources and affect_source and affect_source not in decisive_sources:
        return False, GATE_CHANNEL_ADVISORY

    return True, GATE_OK


def replay_session(
    readings: Sequence[dict[str, Any]],
    *,
    min_confidence: float,
    min_consecutive: int,
    cooldown_cycles: int,
    decisive_sources: Sequence[str],
    adapt_states: Sequence[str],
) -> dict[str, Any]:
    """Walk one session's readings in cycle order and record what the gate would have done.

    Affect history is rebuilt as the walk proceeds, exactly as the profiler builds it live: the
    current reading is folded in BEFORE the gate is consulted, which is why a sustain requirement
    of 2 means "this cycle and the previous one agree" rather than "the two before this one".
    """
    history: list[str] = []
    last_adaptation_cycle: int | None = None
    reasons: dict[str, int] = {}
    interventions: list[dict[str, Any]] = []

    for reading in readings:
        state = reading.get("affect_state")
        if state:
            history.append(state)

        allowed, reason = replay_gate(
            affect_state=state,
            affect_confidence=reading.get("affect_confidence"),
            affect_history=history,
            cycle_number=reading.get("cycle_number"),
            last_adaptation_cycle=last_adaptation_cycle,
            affect_source=reading.get("affect_source"),
            min_confidence=min_confidence,
            min_consecutive=min_consecutive,
            cooldown_cycles=cooldown_cycles,
            decisive_sources=decisive_sources,
            adapt_states=adapt_states,
        )
        reasons[reason] = reasons.get(reason, 0) + 1

        if allowed:
            last_adaptation_cycle = reading.get("cycle_number")
            interventions.append(reading)

    return {
        "cycles": len(readings),
        "interventions": interventions,
        "reasons": reasons,
    }


def _precision(
    interventions: Sequence[dict[str, Any]], self_reports: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """How many interventions landed on a learner who said they needed one.

    Matched by proximity in cycles, because self-reports arrive at section boundaries rather than
    on the cycle clock. Interventions with no self-report nearby are EXCLUDED from the
    denominator rather than counted as unwarranted: no report means no evidence either way, and
    treating silence as "the learner was fine" would systematically understate precision.
    """
    matched = 0
    warranted = 0

    for intervention in interventions:
        cycle = intervention.get("cycle_number")
        if cycle is None:
            continue
        nearby = [
            r
            for r in self_reports
            if r.get("cycle_number") is not None
            and abs(int(r["cycle_number"]) - int(cycle)) <= SELF_REPORT_WINDOW_CYCLES
        ]
        if not nearby:
            continue

        # The NEAREST report in time, not "any negative one in the window". With more than one
        # report in range, "any" is systematically generous: it counts an intervention as
        # warranted whenever a negative report sits anywhere nearby, even when the report
        # closest to the moment said the learner was fine. That inflates precision by exactly
        # the amount the window is widened, which would make the figure an artefact of a
        # constant rather than a measurement.
        nearest = min(nearby, key=lambda r: abs(int(r["cycle_number"]) - int(cycle)))
        matched += 1
        if nearest.get("affect") in NEGATIVE_SELF_REPORTS:
            warranted += 1

    if matched < MIN_PRECISION_SAMPLE:
        return {
            "precision": None,
            "matched_interventions": matched,
            "warranted": warranted,
            "note": (
                f"fewer than {MIN_PRECISION_SAMPLE} interventions had a self-report within "
                f"{SELF_REPORT_WINDOW_CYCLES} cycles; a ratio over this many would not be worth "
                "reporting"
            ),
        }

    return {
        "precision": round(warranted / matched, 4),
        "matched_interventions": matched,
        "warranted": warranted,
        "note": None,
    }


async def _load_sessions(
    db: AsyncSession, *, phase: str | None = None, group: str | None = None
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    """Recorded readings and self-reports, grouped by session and ordered by cycle."""
    stmt = select(ResearchEvent).where(
        ResearchEvent.event_type.in_((*DETECTION_EVENTS, SELF_REPORT_EVENT))
    )
    if phase:
        stmt = stmt.where(ResearchEvent.phase == phase)
    if group:
        stmt = stmt.where(ResearchEvent.group == group)
    stmt = stmt.order_by(
        ResearchEvent.session_id.asc(),
        ResearchEvent.cycle_number.asc(),
        ResearchEvent.sequence_number.asc().nullslast(),
    )

    readings: dict[str, list[dict[str, Any]]] = {}
    reports: dict[str, list[dict[str, Any]]] = {}

    for row in (await db.execute(stmt)).scalars().all():
        payload = row.payload if isinstance(row.payload, dict) else {}
        session = str(row.session_id or "")
        if row.event_type == SELF_REPORT_EVENT:
            reports.setdefault(session, []).append(
                {"cycle_number": row.cycle_number, "affect": payload.get("affect")}
            )
        else:
            readings.setdefault(session, []).append(
                {
                    "cycle_number": row.cycle_number,
                    "affect_state": payload.get("affect_state"),
                    "affect_confidence": payload.get("affect_confidence"),
                    "affect_source": payload.get("affect_source"),
                    "event_type": row.event_type,
                }
            )

    return readings, reports


def _hours(cycles: int) -> float:
    """Cycle count as hours, at the fixed 30-second cadence."""
    return cycles * 30.0 / 3600.0


async def sweep(
    db: AsyncSession,
    *,
    confidence_floors: Iterable[float],
    min_consecutive: int | None = None,
    cooldown_cycles: int | None = None,
    decisive_sources: Sequence[str] | None = None,
    phase: str | None = None,
    group: str | None = None,
) -> dict[str, Any]:
    """Replay every recorded session at each confidence floor and report what would have happened.

    Defaults for the settings not being swept come from the DEPLOYED configuration, so a sweep
    varies one thing at a time against what is actually running rather than against an invented
    baseline.
    """
    # Defaults come from the LIVE configuration, not from constants bound when this module was
    # imported. The thresholds are editable at runtime now, so a replay that defaulted to the
    # process's start-up values would silently compare the record against a gate that is no
    # longer deployed -- and report the difference as though it were a finding.
    live = config_service.get_config()
    consecutive = live.min_consecutive if min_consecutive is None else min_consecutive
    cooldown = live.cooldown_cycles if cooldown_cycles is None else cooldown_cycles
    decisive = list(live.decisive_sources if decisive_sources is None else decisive_sources)

    readings, reports = await _load_sessions(db, phase=phase, group=group)
    total_cycles = sum(len(v) for v in readings.values())

    rows: list[dict[str, Any]] = []
    for floor in confidence_floors:
        interventions: list[dict[str, Any]] = []
        reasons: dict[str, int] = {}
        matched_reports: list[dict[str, Any]] = []

        for session, session_readings in readings.items():
            result = replay_session(
                session_readings,
                min_confidence=floor,
                min_consecutive=consecutive,
                cooldown_cycles=cooldown,
                decisive_sources=decisive,
                adapt_states=live.adapt_states,
            )
            interventions.extend(result["interventions"])
            for reason, count in result["reasons"].items():
                reasons[reason] = reasons.get(reason, 0) + count
            # Precision is computed per session so a cycle number from one session can never be
            # matched against a self-report from another.
            matched_reports.append(
                _precision(result["interventions"], reports.get(session, []))
            )

        matched = sum(m["matched_interventions"] for m in matched_reports)
        warranted = sum(m["warranted"] for m in matched_reports)
        hours = _hours(total_cycles)

        rows.append(
            {
                "min_confidence": round(float(floor), 4),
                "interventions": len(interventions),
                "cycles": total_cycles,
                "interventions_per_hour": (
                    round(len(interventions) / hours, 2) if hours > 0 else None
                ),
                "gate_reasons": reasons,
                "precision": (
                    round(warranted / matched, 4) if matched >= MIN_PRECISION_SAMPLE else None
                ),
                "matched_interventions": matched,
                "warranted_interventions": warranted,
            }
        )

    return {
        "sessions": len(readings),
        "cycles": total_cycles,
        "self_reports": sum(len(v) for v in reports.values()),
        "held_fixed": {
            "min_consecutive": consecutive,
            "cooldown_cycles": cooldown,
            "decisive_sources": decisive,
            "adapt_states": list(live.adapt_states),
        },
        "rows": rows,
        # Stated in the response, not only in the docs. A sweep table is the kind of output that
        # gets pasted into a chapter, and the caveat needs to travel with it.
        "caveat": (
            "Replays recorded readings only. A higher floor can only remove interventions that "
            "were recorded; it cannot invent a cycle the detector never scored. Precision counts "
            "only interventions with a self-report within "
            f"{SELF_REPORT_WINDOW_CYCLES} cycles, and is null below {MIN_PRECISION_SAMPLE} of them."
        ),
    }
