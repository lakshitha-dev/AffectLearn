"""Conditional routing + the adaptation gate for the agent graph (Story 4.4).

Pure functions (no I/O) so they are unit-testable in isolation.

ELIGIBILITY (`should_adapt`) follows the architecture (lines 166-174): in Phase A
(non-adaptive data collection, FR28) or for the control group, the cycle goes to
`log_only` and ENDs — no adaptation. Only Phase B + adaptive group is eligible.

THE GATE (`passes_adaptation_gate`) is the second half of the decision, and it exists
because eligibility alone is not enough. The affect detector is imperfect — the facial
branch sits at a deployed weighted-F1 of ~0.47-0.48 and behaviour-only detection tops out
around 0.70 AUC in the literature — so acting on every cycle means acting on noise. Without
a gate a 0.26-confidence guess triggers the same intervention as a 0.95 one, and the state
can flip every 30 seconds, giving the learner whiplash.

Gating turns detector error into INACTION rather than into a WRONG INTERVENTION, which is
the honest engineering answer to a ceiling you cannot raise. It also implements the
temporal-trend reasoning the thesis already describes ("sustained confusion across two or
more cycles"), which previously existed only as prose: the LLM was shown
`recent_affect_history` in its prompt and left to self-moderate. Relying on that is exactly
the failure mode Puech et al. document — LLM-self-selected pedagogical intents underperform
expert-designed ones — so the persistence rule belongs in code, not in a prompt.

All four thresholds are env-tunable so the pilot can be re-calibrated without a code change.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

import structlog

from app.agents.state import (
    AFFECT_SOURCE_BEHAVIORAL,
    AFFECT_SOURCE_CATEGORY,
    AFFECT_SOURCE_ENGAGEMENT,
    AFFECT_SOURCE_FACIAL_GEOMETRY,
    AFFECT_SOURCE_PERFORMANCE,
    AFFECT_SOURCE_FUSION,
    AgentState,
)

# Conditional-edge route keys (graph node names).
ROUTE_LOG_ONLY = "log_only"
ROUTE_PEDAGOGICAL = "pedagogical"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# Minimum softmax confidence in the chosen affect before it may drive an intervention.
#
# CALIBRATED 14 Aug 2026 against real out-of-fold predictions from the behavioural confusion model
# (DUX v0+v1, 1,419 windows, 46 participants, leave-one-participant-out — see
# affectlearn-ml/reports/dux_confusion/FINDINGS.md). Simulating this exact gate over those
# predictions, with ADAPT_MIN_CONSECUTIVE = 2 and ADAPT_COOLDOWN_CYCLES = 3:
#
#   threshold   precision   interventions/hour   one every
#   -------------------------------------------------------
#   (no gate)       0.181            120.0        30 s
#   0.55            0.391              5.4        11 min
#   0.60            0.429              4.1        15 min
#   0.65            0.400              2.5        24 min
#   0.70            0.500              1.5        39 min      <- chosen
#
# 0.55 was an unvalidated guess. 0.70 is where measured precision peaks, and it cuts interruptions
# from 5.4/hour to 1.5/hour. The metric is PRECISION, not recall, because the cost of the two errors
# is asymmetric: a hint shown to a learner who was coping is mildly redundant, while an intervention
# fired on a false positive actively interrupts someone who was fine. Recall is deliberately
# sacrificed — a missed confused window is usually followed by another one, since confusion persists.
#
# Two limits on this calibration, both of which mean it should be re-measured on platform data:
#   * DUX participants used business software, not learning material.
#   * The simulation treated adjacent surviving windows as consecutive in time; windows with fewer
#     than 5 events were dropped at load, which the live pipeline does not do.
ADAPT_MIN_CONFIDENCE = _env_float("ADAPT_MIN_CONFIDENCE", 0.70)

# PER-CHANNEL floors, because the two deployed channels were calibrated separately and their
# probability distributions are not comparable. `ADAPT_MIN_CONFIDENCE` remains the default for any
# channel without an override, so existing behaviour is unchanged for the behavioural channel.
#
# The measured basis (evaluation/gate_calibration.py and geometry_gate_calibration.py, both with
# persistence 2 and cooldown 3, intervals resampling participants):
#
#   channel            floor   gated precision        interventions/h
#   behavioural        0.50    0.500 [0.273, 0.737]   ~1.5      <- WAS deployed; raised to 0.70
#   facial geometry    0.50    0.763 [0.635, 0.853]   ~10.3
#   facial geometry    0.70    0.872 [0.783, 0.937]   ~7.1      <- chosen
#
# A single global floor would force one of these to use the other's operating point. Raising the
# global value to 0.70 would move the behavioural channel off the setting it was tuned to; leaving
# it at 0.50 would give away 0.109 of precision on the geometry channel for no reason.
_CHANNEL_MIN_CONFIDENCE: dict[str, float] = {
    AFFECT_SOURCE_FACIAL_GEOMETRY: _env_float("ADAPT_MIN_CONFIDENCE_GEOMETRY", 0.70),
    # RAISED from the 0.50 the deployment was running (2026-09), where measured precision at that
    # operating point is 0.500 [0.273, 0.737] -- a coin flip. Half of every confusion intervention
    # was firing on a learner who was not confused, which is not a threshold that can support a
    # claim about whether confusion interventions help.
    #
    # Stated EXPLICITLY here rather than left to fall through to `ADAPT_MIN_CONFIDENCE`, because
    # the deployment overrides that global to 0.50 for other reasons; an inherited floor would
    # silently drop this channel back to the coin flip. Fewer, better-founded triggers is the
    # right trade when the detector is this weak -- and the confusion literature agrees for an
    # unrelated reason: confusion that resolves on its own teaches better than confusion that is
    # interrupted (D'Mello et al. 2014), so a late, confident trigger is preferable anyway.
    AFFECT_SOURCE_BEHAVIORAL: _env_float("ADAPT_MIN_CONFIDENCE_BEHAVIORAL", 0.70),
    # The performance channel's "confidence" is a weighted count of observed behaviours, not a
    # calibrated probability, so it does not share an operating point with either model. 0.60 is
    # CHOSEN, not calibrated: it sits where at least two independent indicators must be present,
    # so no single measure triggers an intervention alone. The pilot can calibrate it from real
    # cycles the way the other two were.
    AFFECT_SOURCE_PERFORMANCE: _env_float("ADAPT_MIN_CONFIDENCE_PERFORMANCE", 0.60),
}


def min_confidence_for(affect_source: str | None) -> float:
    """The confidence floor this channel must clear. Falls back to the global setting."""
    if affect_source and affect_source in _CHANNEL_MIN_CONFIDENCE:
        return _CHANNEL_MIN_CONFIDENCE[affect_source]
    return ADAPT_MIN_CONFIDENCE

# How many consecutive cycles must agree on the state. The profiler appends the CURRENT
# affect before the gate runs, so 2 means "this cycle and the previous one agree".
ADAPT_MIN_CONSECUTIVE = _env_int("ADAPT_MIN_CONSECUTIVE", 2)

# Cycles that must elapse after an adaptation before another may fire (~30s per cycle).
ADAPT_COOLDOWN_CYCLES = _env_int("ADAPT_COOLDOWN_CYCLES", 3)

# States that may trigger an intervention. `engaged` is deliberately absent: the design
# leaves engagement undisturbed, and it is also the state the detector is worst at, so
# acting on it spends the learner's attention on the least reliable signal.
ADAPT_STATES: tuple[str, ...] = tuple(
    s.strip() for s in os.getenv("ADAPT_STATES", "bored,confused,frustrated").split(",") if s.strip()
)

# `gate_reason` values — stable strings, safe to aggregate over in analysis.
logger = structlog.get_logger(__name__)

GATE_OK = "ok"
GATE_NOT_ELIGIBLE = "not_eligible"
GATE_NO_AFFECT = "no_affect"
GATE_STATE_NOT_ACTIONABLE = "state_not_actionable"
GATE_LOW_CONFIDENCE = "low_confidence"
GATE_NOT_SUSTAINED = "not_sustained"
GATE_COOLDOWN = "cooldown"
# The channel is inferred and logged, but is not authorised to intervene alone.
GATE_CHANNEL_ADVISORY = "channel_advisory"
# The cycle cleared EVERY gate condition and was then withheld by the randomised trial draw.
# This is not a failure: it is the control arm, and the cycles carrying it are the comparison
# group the delivered arm is measured against.
GATE_WITHHELD_RANDOM = "withheld_random"

# ── the randomised trial arm ──────────────────────────────────────────────────────────
#
# WHY THE SYSTEM DELIBERATELY WITHHOLDS HELP FROM SOME QUALIFYING MOMENTS.
#
# An intervention fires when the detector is MOST confident the learner is bored or confused --
# which is, by construction, near the peak of that state. States drift back toward baseline on
# their own, so the cycles after any trigger improve whether or not anything was delivered.
# Measuring only delivered cycles therefore reports regression to the mean as an intervention
# effect, and reports it as a positive result. No amount of care downstream recovers from that.
#
# So the gate decides ELIGIBILITY and this draw decides DELIVERY. The withheld cycles are matched
# to the delivered ones on every gate condition -- same state, same confidence floor, same
# persistence, same cooldown -- because they are drawn from exactly the same set. That makes them
# a valid control, and it makes the detector's own later readings a valid outcome measure: any
# bias in the detector applies equally to both arms and cancels out of the difference.
ADAPT_WITHHOLD_RATE = _env_float("ADAPT_WITHHOLD_RATE", 0.35)

#: `arm` values recorded on the research event. `None` means the cycle never became eligible,
#: so it belongs to neither arm and must be excluded from the trial analysis.
ARM_DELIVERED = "delivered"
ARM_WITHHELD = "withheld"


def withhold_draw(learner_id: Any, session_id: Any, cycle_number: Any) -> float:
    """A uniform [0, 1) draw that is a pure function of the cycle's identity.

    Hashed rather than sampled from `random`: a PRNG's output depends on process state, so the
    same cycle would draw differently on a replay, in a test, or after a restart -- and the
    assignment would then be unauditable. Hashing the identity means `gate_replay_service` can
    re-derive every historical arm exactly, months later, from the event record alone.
    """
    key = f"{learner_id}|{session_id}|{cycle_number}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big") / 2**64


def consumes_cooldown(gate_reason: str) -> bool:
    """Whether this verdict spends the cooldown window.

    A withheld cycle MUST spend it exactly as a delivered one does. If it did not, the control
    arm would become eligible again sooner, drift to a higher trigger rate, and stop being
    matched to the delivered arm -- which is the whole basis of the comparison.
    """
    return gate_reason in (GATE_OK, GATE_WITHHELD_RANDOM)


def arm_for(gate_reason: str) -> str | None:
    """Which trial arm this cycle belongs to, or None if it never became eligible."""
    if gate_reason == GATE_OK:
        return ARM_DELIVERED
    if gate_reason == GATE_WITHHELD_RANDOM:
        return ARM_WITHHELD
    return None


def should_adapt(state: AgentState) -> bool:
    """ELIGIBILITY only: True on the Phase B / adaptive-group path.

    Unchanged from Story 4.4 — the gate is applied on top of this, not instead of it, so the
    tri-modal phase/group contract and its tests are untouched.
    """
    return state.get("phase") == "phase_b" and state.get("group") == "adaptive"


# ── which channels may DRIVE an intervention ──────────────────────────────────────────
# The gate thresholds a model's SELF-REPORTED confidence in the moment. That is not the same
# question as whether the channel is any good, and on this platform the two diverge sharply:
# the behavioural channel reaches AUC 0.7408-0.7473 with a bootstrap interval excluding chance
# and a within-participant permutation p of 0.0005, while the facial channel is indistinguishable
# from chance on the only corpus where both are recorded against one human label (AUC 0.5064,
# p = 0.108) and in production emits P(confused) inside a 0.127-wide band centred on 0.502.
#
# Because each modality arrives on its own WebSocket message, each runs the whole graph and each
# gets its own gate evaluation, so BOTH channels are independently decisive. A fixed threshold
# against a distribution centred on the threshold fires on roughly half of all cycles whatever
# signal is carried, which means the weaker channel triggers MORE interventions than the stronger
# one. `AFFECT_DETECTION_MODE=behavioral_only` does not prevent this -- it only skips fusion
# pairing, leaving both channels deciding alone.
#
# So intervention authority is granted by measured reliability rather than momentary confidence.
# A non-decisive channel is still inferred, still logged, and still available for fusion research
# and for corroboration; it simply cannot interrupt a learner on its own. Set to an empty string
# to let every channel decide, which restores the previous behaviour exactly.
#
# AFFECT_SOURCE_FACIAL_GEOMETRY is decisive on the same evidential standard, not by analogy to the
# facial channel above. It is a different model on a different construct, and the number the gate
# actually depends on was measured for it directly (reports/engagenet_screen/gate_calibration.json,
# regenerable via evaluation/geometry_gate_calibration.py):
#
#     channel                threshold   gated precision      95% CI
#     behavioural            0.70        0.500                [0.273, 0.737]
#     facial geometry        0.70        0.872                [0.783, 0.937]
#
# Detection quality agrees: AUC 0.9225 [0.889, 0.948] on EngageNet's held-out test split, 26
# participants disjoint from training, within-participant permutation p at the 0.0005 floor. The
# failure mode described above cannot recur here for a structural reason as well as an empirical
# one -- that channel's probabilities occupied a 0.127-wide band, and this one's span 0.968.
#
# One caveat that belongs beside the grant rather than in a report: the same calibration puts this
# channel at 7.1 interventions/hour against the behavioural channel's ~1.5. Precision is high, so
# these are mostly warranted, but EngageNet is continuously recorded video at a 31% base rate and
# platform sessions are neither. The deployed RATE is not established by this corpus and is a
# question for the pilot; if it proves too frequent, raise ADAPT_COOLDOWN_CYCLES for this channel
# rather than the confidence floor, since precision is not the problem.
DECISIVE_AFFECT_SOURCES: tuple[str, ...] = tuple(
    s.strip() for s in os.getenv(
        "DECISIVE_AFFECT_SOURCES",
        f"{AFFECT_SOURCE_BEHAVIORAL},{AFFECT_SOURCE_FUSION},{AFFECT_SOURCE_FACIAL_GEOMETRY}",
    ).split(",") if s.strip()
)


# The provenance markers that exist. A source outside this set means a channel was added
# without being classified, which is a configuration gap rather than a runtime condition.
_KNOWN_AFFECT_SOURCES = frozenset({
    AFFECT_SOURCE_BEHAVIORAL, AFFECT_SOURCE_FUSION,
    AFFECT_SOURCE_CATEGORY, AFFECT_SOURCE_ENGAGEMENT,
    AFFECT_SOURCE_FACIAL_GEOMETRY, AFFECT_SOURCE_PERFORMANCE,
})


def is_decisive(affect_source: str | None) -> bool:
    """Whether a reading from this channel may trigger an intervention on its own.

    An allowlist, so anything absent from it is non-decisive -- including a channel added later
    and never classified. That is the safe direction for an intervention (the cost of a missed
    window is another window; the cost of a wrong interruption is a learner interrupted while
    coping), but it must never be SILENT: a new channel that quietly never intervenes would be
    indistinguishable, during a pilot, from a system that cannot intervene at all. So an
    unrecognised source is logged at warning level every time it is evaluated.

    A MISSING source fails open. The gate is called directly by tests and by callers that
    predate provenance, and those must behave exactly as they did.
    """
    if not DECISIVE_AFFECT_SOURCES:
        return True
    if not affect_source:
        return True
    if affect_source not in _KNOWN_AFFECT_SOURCES:
        logger.warning(
            "affect_source_unclassified",
            affect_source=affect_source,
            decisive_sources=list(DECISIVE_AFFECT_SOURCES),
            consequence="treated as advisory; it will never trigger an adaptation",
        )
        return False
    return affect_source in DECISIVE_AFFECT_SOURCES


def passes_adaptation_gate(
    affect_state: str | None,
    affect_confidence: float | None,
    affect_history: list | None,
    cycle_number: int | None,
    last_adaptation_cycle: int | None,
    affect_source: str | None = None,
) -> tuple[bool, str]:
    """Pure gate. Returns `(allowed, reason)`; `reason` is one of the `GATE_*` constants.

    `affect_history` is the profile's history INCLUDING the current cycle (the profiler folds
    the current affect in before calling this). `last_adaptation_cycle` is None when this
    learner has never been adapted.
    """
    if not affect_state:
        return False, GATE_NO_AFFECT

    if affect_state not in ADAPT_STATES:
        return False, GATE_STATE_NOT_ACTIONABLE

    if float(affect_confidence or 0.0) < min_confidence_for(affect_source):
        return False, GATE_LOW_CONFIDENCE

    need = max(1, ADAPT_MIN_CONSECUTIVE)
    recent = list(affect_history or [])[-need:]
    if len(recent) < need or any(a != affect_state for a in recent):
        return False, GATE_NOT_SUSTAINED

    if last_adaptation_cycle is not None and cycle_number is not None:
        if int(cycle_number) - int(last_adaptation_cycle) < ADAPT_COOLDOWN_CYCLES:
            return False, GATE_COOLDOWN

    # Evaluated LAST, deliberately. Checking authority earlier would mask the binding
    # constraint: every withheld advisory cycle would read `channel_advisory` whether the
    # reading was sustained and confident or nowhere near it. Placed here, the reason names
    # what actually stopped the cycle, and `channel_advisory` appears ONLY when the channel
    # would otherwise have intervened -- which makes the count of those cycles a direct
    # measurement of what the advisory channel would have done, and therefore evidence for or
    # against promoting it later. The same reason the idle-window suppression records
    # `would_have_been` rather than discarding it.
    if not is_decisive(affect_source):
        return False, GATE_CHANNEL_ADVISORY

    return True, GATE_OK


def adaptation_decision(
    state: AgentState,
    profile: dict | None,
    last_adaptation_cycle: int | None,
) -> tuple[bool, str]:
    """Combine eligibility and the gate. Pure — the caller supplies the fresh profile.

    Takes `profile` explicitly rather than reading `state["learner_profile"]` because the
    profiler computes the new profile locally and returns it; at the moment the decision is
    made it is NOT yet in `state`. Reading it from state there would silently use the
    PREVIOUS cycle's affect history.
    """
    if not should_adapt(state):
        return False, GATE_NOT_ELIGIBLE
    # Per-channel history, not the interleaved one: the graph runs once per modality per cycle,
    # so the last two entries of `affect_history` are usually the two channels disagreeing
    # inside a single cycle rather than one state holding across two -- which made the
    # consecutive-cycle condition effectively unsatisfiable. See profile_service.apply_affect.
    from app.services.profile_service import sustain_history

    allowed, reason = passes_adaptation_gate(
        state.get("affect_state"),
        state.get("affect_confidence"),
        sustain_history(profile or {}, state.get("affect_source")),
        state.get("cycle_number"),
        last_adaptation_cycle,
        state.get("affect_source"),
    )
    if not allowed:
        return False, reason

    # Applied LAST, and only to cycles that already cleared everything else, so the withheld set
    # is exactly the eligible set. Drawing earlier would withhold cycles that would have failed
    # the gate anyway, which would put unmatched cycles in the control arm and bias the contrast.
    rate = min(1.0, max(0.0, ADAPT_WITHHOLD_RATE))
    if rate > 0.0 and withhold_draw(
        state.get("learner_id"), state.get("session_id"), state.get("cycle_number")
    ) < rate:
        return False, GATE_WITHHELD_RANDOM

    return True, GATE_OK


def route_after_profiler(state: AgentState) -> str:
    """Map the adaptation decision to the next node key for the conditional edge.

    Prefers the `should_adapt` flag the profiler already wrote (it is the only place with the
    fresh profile and therefore the only place that can evaluate the gate). Falls back to
    bare eligibility when the flag is absent, which keeps the router usable standalone and
    preserves the Story 4.4 / 6.1 routing tests.
    """
    decided = state.get("should_adapt")
    allowed = should_adapt(state) if decided is None else bool(decided)
    return ROUTE_PEDAGOGICAL if allowed else ROUTE_LOG_ONLY
