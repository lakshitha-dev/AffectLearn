"""Conditional routing + the adaptation gate for the agent graph (Story 4.4).

Pure functions (no I/O) so they are unit-testable in isolation.

ELIGIBILITY (`should_adapt`) follows the architecture (lines 166-174): in Phase A
(non-adaptive data collection, FR28) or for the control group, the cycle goes to
`log_only` and ENDs — no adaptation. Only Phase B + adaptive group is eligible.

THE GATE (`passes_adaptation_gate`) is the second half of the decision, and it exists
because eligibility alone is not enough. The affect detectors are imperfect — the deployed
behavioural confusion model reaches AUC 0.734 on DUX (leave-one-session-out, raw features), and
even the facial-geometry disengagement model (AUC 0.922 on EngageNet test) is wrong on a share of
windows — so acting on every cycle means acting on noise. Without
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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.services.config_service import GateConfig as GateConfigLike

import structlog

from app.agents.state import (
    AFFECT_SOURCE_BEHAVIORAL,
    AFFECT_SOURCE_CATEGORY,
    AFFECT_SOURCE_ENGAGEMENT,
    AFFECT_SOURCE_FACIAL_GEOMETRY,
    AFFECT_SOURCE_PERFORMANCE,
    AFFECT_SOURCE_FUSION,
    AFFECT_SOURCE_LEARNER_REQUEST,
    AgentState,
)
# The learner-side holds (open card, section change, "Got it"...). Imported into this namespace so
# the monitor's completeness check, which reads every GATE_* here, sees them too.
from app.agents.delivery_guard import (  # noqa: E402,F401
    GATE_CARD_OPEN,
    GATE_LADDER_EXHAUSTED,
    GATE_PAGE_HIDDEN,
    GATE_QUIZ_ACTIVE,
    GATE_RECENT_HELP,
    GATE_RESOLVED,
    GATE_SECTION_GRACE,
    GATE_STALE_SECTION,
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
#   0.55            0.368              5.8        10 min
#   0.60            0.412              4.3        14 min
#   0.65            0.367              2.5        24 min
#   0.70            0.500              1.5        39 min      <- chosen
#
# (reports/dux_v1_z/gate_calibration.json. These predictions are session-z-scored; the deployed
# model uses raw features, so the sweep may flatter it slightly.)
#
# 0.55 was an unvalidated guess. 0.70 is where measured precision peaks, and it cuts interruptions
# from 5.8/hour to 1.5/hour. The floor was chosen from this same sweep, so 0.500 is an in-sample
# figure resting on 18 offers. The metric is PRECISION, not recall, because the cost of the two errors
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
#   behavioural        0.70    0.500 [0.273, 0.737]   ~1.5      <- deployed (was 0.50 until Sep 2026)
#   facial geometry    0.50    0.763 [0.635, 0.853]   ~10.3
#   facial geometry    0.70    0.872 [0.783, 0.937]   ~7.1      <- chosen
#
# A single global floor would force one of these to use the other's operating point. Raising the
# global value to 0.70 would move the behavioural channel off the setting it was tuned to; leaving
# it at 0.50 would give away 0.109 of precision on the geometry channel for no reason.
_CHANNEL_MIN_CONFIDENCE: dict[str, float] = {
    AFFECT_SOURCE_FACIAL_GEOMETRY: _env_float("ADAPT_MIN_CONFIDENCE_GEOMETRY", 0.70),
    # RAISED from the 0.50 the deployment was running (2026-09). The 0.50 floor was never swept
    # for this channel; at 0.55 the measured precision is only 0.368, and even the chosen 0.70
    # reaches 0.500 [0.273, 0.737] -- a coin flip, on 18 offers. A floor that fires on more
    # learners who are not confused than on learners who are cannot support a claim about whether
    # confusion interventions help.
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

# Length of one sensing cycle, used to measure the cooldown on the SERVER clock.
#
# The cooldown used to subtract client `cycle_number` values. Those are not a clock: each channel's
# hook keeps its own counter, and every counter restarts at 1 when the lesson page remounts, while
# the session (and the marker) carry on. An offer at cycle 40 in one lesson therefore held the next
# lesson in `cooldown` until its counter climbed back past 43 -- about 20 minutes of silence -- and
# a facial and a behavioural counter that started at different moments disagreed even within one
# lesson. Elapsed server time, rounded to whole cycles, measures the same "three cycles" without
# trusting a counter the client resets.
ADAPT_CYCLE_SECONDS = max(1, _env_int("ADAPT_CYCLE_SECONDS", 30))

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
# The learner has already had this session's full allowance of interventions.
GATE_SESSION_CAP = "session_cap"
# NOT a withholding reason: the learner explicitly asked for the next step from a card already on
# screen. Recorded under its own name so it never counts as a detector-driven pass (`ok`) and
# never enters either trial arm.
GATE_LEARNER_REQUEST = "learner_request"

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

# Most interventions one session may produce, counted across BOTH arms.
#
# There was no ceiling at all before this. The geometry channel triggers at roughly 7.1/hour and
# each modality runs the gate independently, so a long session could deliver an intervention every
# ~90 seconds indefinitely. Past some rate the study stops measuring whether help helps and starts
# measuring how people respond to being interrupted -- and the states it interrupts them about are
# exactly the ones repeated interruption produces.
ADAPT_MAX_PER_SESSION = _env_int("ADAPT_MAX_PER_SESSION", 6)

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


def _session_cap_reached(
    profile: dict, session_id: Any, config: "GateConfigLike | None" = None
) -> bool:
    """Whether this session has already used its allowance.

    The counter is session-scoped the same way the cooldown marker is: the profile outlives the
    session, so a count carried over from an earlier session would suppress interventions in this
    one from its first cycle.

    SCOPE OF "SESSION". `session_id` is the platform session, not a lesson: `connection_manager`
    keeps one per learner for the life of the server process, reused across lesson navigation and
    reconnects, and after a restart it is resumed from the Redis session record (12 h sliding
    TTL, refreshed by every message). The cap therefore bounds offers across every lesson a learner
    studies in that platform session, and a new session starts only on a new process with no
    recent session record.
    """
    if profile.get("adaptation_session_id") != session_id:
        return False
    cap = config.max_per_session if config else ADAPT_MAX_PER_SESSION
    return int(profile.get("eligible_this_session", 0) or 0) >= max(0, cap)


def record_eligible_cycle(profile: dict, session_id: Any) -> None:
    """Count a cycle that entered the trial. Mutates `profile` in place.

    Counts BOTH arms: a withheld cycle used up an eligible moment just as a delivered one did,
    and the cap exists to bound how much of the session the trial occupies, not how much help
    was given.
    """
    if profile.get("adaptation_session_id") != session_id:
        profile["adaptation_session_id"] = session_id
        profile["eligible_this_session"] = 0
    profile["eligible_this_session"] = int(profile.get("eligible_this_session", 0) or 0) + 1


def _ladder_key(section_id: Any, affect_state: Any) -> str:
    """Rungs are tracked per SECTION and per STATE.

    Per section, because escalation is about this material: a learner confused by recursion and
    later bored by an easy example are two independent situations, and carrying a deep rung across
    them would open with the heaviest intervention on material the learner has not yet struggled
    with. Per state for the same reason — the ladders are different ladders.
    """
    return f"{section_id or '-'}|{affect_state or '-'}"


def current_rung(profile: dict, session_id: Any, section_id: Any, affect_state: Any) -> int:
    """How many interventions this learner has already been DELIVERED here, for this state.

    Session-scoped like the cooldown marker and the cap: a rung carried in from an earlier
    session would open a fresh session at the deepest intervention.
    """
    if profile.get("adaptation_session_id") != session_id:
        return 0
    rungs = profile.get("ladder_rungs")
    if not isinstance(rungs, dict):
        return 0
    return int(rungs.get(_ladder_key(section_id, affect_state), 0) or 0)


def record_delivered_rung(
    profile: dict, session_id: Any, section_id: Any, affect_state: Any
) -> None:
    """Advance the ladder. Mutates `profile` in place.

    Advanced on DELIVERY only, unlike the cap and the cooldown which both arms spend. A withheld
    cycle showed the learner nothing, so nothing was tried and nothing has been ruled out — the
    next delivered intervention must still start where this one would have. (This does not
    desynchronise the arms: the rung decides WHAT is delivered, never WHETHER.)
    """
    if profile.get("adaptation_session_id") != session_id:
        profile["adaptation_session_id"] = session_id
        profile["ladder_rungs"] = {}
        profile["eligible_this_session"] = 0
    rungs = profile.setdefault("ladder_rungs", {})
    if not isinstance(rungs, dict):
        rungs = profile["ladder_rungs"] = {}
    key = _ladder_key(section_id, affect_state)
    rungs[key] = int(rungs.get(key, 0) or 0) + 1


def consumes_cooldown(gate_reason: str) -> bool:
    """Whether this verdict spends the cooldown window and the session cap.

    A withheld cycle MUST spend them exactly as a delivered one does. If it did not, the control
    arm would become eligible again sooner, drift to a higher trigger rate, and stop being
    matched to the delivered arm -- which is the whole basis of the comparison.

    WHEN they are spent differs. A withheld cycle is complete at the gate, so the profiler spends
    them there. An `ok` cycle has not shown the learner anything yet -- the strategist may still
    choose `no_action`, the adapter may drop a duplicate, the socket may drop a stale card or fail
    to send -- so it spends them only when a card actually reaches the learner (`commit_offer`).
    """
    return gate_reason in (GATE_OK, GATE_WITHHELD_RANDOM)


def stamp_offer(profile: dict, session_id: Any, now_ms: int) -> None:
    """Start the cooldown at `now_ms` on the server clock. Mutates `profile` in place.

    The session is stamped beside it so a marker left by an earlier session is recognisable and
    ignored rather than trusted (see `cycles_since_offer`).
    """
    profile["last_adaptation_ms"] = int(now_ms)
    profile["last_adaptation_session"] = session_id
    # The pre-fix marker compared client cycle numbers; drop it so nothing reads it by mistake.
    profile.pop("last_adaptation_cycle", None)


def cycles_since_offer(
    profile: dict, session_id: Any, now_ms: int, cycle_seconds: int | None = None
) -> int | None:
    """Whole cycles elapsed since this session's last offer, or None if it has had none.

    Rounded to the nearest cycle rather than floored: windows arrive every 30 s with a little
    jitter, so the third window after an offer lands at 89.9 s as often as at 90.1 s, and flooring
    would turn "three cycles" into four about half the time.
    """
    if profile.get("last_adaptation_session") != session_id:
        return None
    last = profile.get("last_adaptation_ms")
    if last is None:
        return None
    cycle_ms = 1000 * (cycle_seconds or ADAPT_CYCLE_SECONDS)
    return max(0, int(round((int(now_ms) - int(last)) / cycle_ms)))


def pending_offer(state: AgentState, gate_reason: str) -> dict | None:
    """What a passing cycle will spend IF its card is delivered, or None if it spends nothing.

    Carried through the graph to the socket handler, which applies it with `commit_offer` after a
    successful send. Captured here, at the gate, because the section and state are the ones the
    gate ruled on.
    """
    if gate_reason not in (GATE_OK, GATE_LEARNER_REQUEST):
        return None
    return {
        "gate_reason": gate_reason,
        "session_id": state.get("session_id"),
        "section_id": (state.get("content_context") or {}).get("section_id"),
        "affect_state": state.get("affect_state"),
    }


def commit_offer(profile: dict, offer: dict | None, now_ms: int) -> bool:
    """Spend what a DELIVERED card costs. Mutates `profile` in place; returns whether it did.

    A detector-driven card (`ok`) starts the cooldown, counts toward the session cap and advances
    the ladder. A card the learner asked for (`learner_request`) advances the ladder only: the
    cooldown and the cap pace the DETECTOR and are not a budget on help the learner requested.
    """
    if not offer:
        return False
    reason = offer.get("gate_reason")
    session_id = offer.get("session_id")
    if reason == GATE_OK:
        stamp_offer(profile, session_id, now_ms)
        record_eligible_cycle(profile, session_id)
    elif reason != GATE_LEARNER_REQUEST:
        return False
    record_delivered_rung(profile, session_id, offer.get("section_id"), offer.get("affect_state"))
    return True


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
    AFFECT_SOURCE_LEARNER_REQUEST,
})


def is_decisive(affect_source: str | None, sources: tuple[str, ...] | None = None) -> bool:
    """Whether a reading from this channel may trigger an intervention on its own.

    An allowlist, so anything absent from it is non-decisive -- including a channel added later
    and never classified. That is the safe direction for an intervention (the cost of a missed
    window is another window; the cost of a wrong interruption is a learner interrupted while
    coping), but it must never be SILENT: a new channel that quietly never intervenes would be
    indistinguishable, during a pilot, from a system that cannot intervene at all. So an
    unrecognised source is logged at warning level every time it is evaluated.

    A MISSING source fails open. The gate is called directly by tests and by callers that
    predate provenance, and those must behave exactly as they did.

    `sources` overrides the module constant, for the runtime-editable config. It is a parameter
    rather than a second implementation so the two paths CANNOT diverge: the fail-open rules above
    are subtle enough that a duplicated membership test silently lost them once already.
    """
    allowed = DECISIVE_AFFECT_SOURCES if sources is None else sources
    if not allowed:
        return True
    if not affect_source:
        return True
    if affect_source not in _KNOWN_AFFECT_SOURCES:
        logger.warning(
            "affect_source_unclassified",
            affect_source=affect_source,
            decisive_sources=list(allowed),
            consequence="treated as advisory; it will never trigger an adaptation",
        )
        return False
    return affect_source in allowed


def passes_adaptation_gate(
    affect_state: str | None,
    affect_confidence: float | None,
    affect_history: list | None,
    cycle_number: int | None,
    last_adaptation_cycle: int | None,
    affect_source: str | None = None,
    config: "GateConfigLike | None" = None,
) -> tuple[bool, str]:
    """Pure gate. Returns `(allowed, reason)`; `reason` is one of the `GATE_*` constants.

    `affect_history` is the profile's history INCLUDING the current cycle (the profiler folds
    the current affect in before calling this). `last_adaptation_cycle` is None when this
    learner has never been adapted.

    `config` carries runtime-editable thresholds from the admin settings page. It is OPTIONAL and
    defaults to the module constants, which keeps this function pure and keeps every existing
    caller and test working unchanged — the settings feature adds a parameter rather than taking
    a dependency on a service. It is duck-typed rather than imported, because `config_service`
    imports this module and a real import would be circular.
    """
    states = tuple(config.adapt_states) if config else ADAPT_STATES
    floor = (config.min_confidence_for(affect_source) if config
             else min_confidence_for(affect_source))
    need_consecutive = config.min_consecutive if config else ADAPT_MIN_CONSECUTIVE
    cooldown = config.cooldown_cycles if config else ADAPT_COOLDOWN_CYCLES
    decisive = is_decisive(affect_source, tuple(config.decisive_sources) if config else None)
    if not affect_state:
        return False, GATE_NO_AFFECT

    if affect_state not in states:
        return False, GATE_STATE_NOT_ACTIONABLE

    if float(affect_confidence or 0.0) < floor:
        return False, GATE_LOW_CONFIDENCE

    need = max(1, need_consecutive)
    recent = list(affect_history or [])[-need:]
    if len(recent) < need or any(a != affect_state for a in recent):
        return False, GATE_NOT_SUSTAINED

    if last_adaptation_cycle is not None and cycle_number is not None:
        if int(cycle_number) - int(last_adaptation_cycle) < cooldown:
            return False, GATE_COOLDOWN

    # Evaluated LAST, deliberately. Checking authority earlier would mask the binding
    # constraint: every withheld advisory cycle would read `channel_advisory` whether the
    # reading was sustained and confident or nowhere near it. Placed here, the reason names
    # what actually stopped the cycle, and `channel_advisory` appears ONLY when the channel
    # would otherwise have intervened -- which makes the count of those cycles a direct
    # measurement of what the advisory channel would have done, and therefore evidence for or
    # against promoting it later. The same reason the idle-window suppression records
    # `would_have_been` rather than discarding it.
    if not decisive:
        return False, GATE_CHANNEL_ADVISORY

    return True, GATE_OK


def adaptation_decision(
    state: AgentState,
    profile: dict | None,
    last_adaptation_cycle: int | None,
    config: "GateConfigLike | None" = None,
    *,
    cycles_since_last_offer: int | None = None,
) -> tuple[bool, str]:
    """Combine eligibility and the gate. Pure — the caller supplies the fresh profile.

    Takes `profile` explicitly rather than reading `state["learner_profile"]` because the
    profiler computes the new profile locally and returns it; at the moment the decision is
    made it is NOT yet in `state`. Reading it from state there would silently use the
    PREVIOUS cycle's affect history.

    `cycles_since_last_offer` is the cooldown measured on the server clock (`cycles_since_offer`),
    which is what the profiler supplies. When given it replaces the `cycle_number` arithmetic;
    `last_adaptation_cycle` remains for direct callers and tests that reason in cycle numbers.
    """
    if cycles_since_last_offer is not None:
        cooldown_now, cooldown_last = int(cycles_since_last_offer), 0
    else:
        cooldown_now, cooldown_last = state.get("cycle_number"), last_adaptation_cycle
    if not should_adapt(state):
        return False, GATE_NOT_ELIGIBLE
    # The learner asked. Eligibility still applies -- a control-arm learner is never shown a card
    # to ask from, and must not be able to reach the strategist this way either -- but nothing
    # below does: the confidence floor, persistence, cooldown, session cap and trial draw all exist
    # to restrain a DETECTOR, and withholding help a learner explicitly requested would be the
    # system overruling the one reading it cannot get wrong.
    if state.get("affect_source") == AFFECT_SOURCE_LEARNER_REQUEST:
        return True, GATE_LEARNER_REQUEST
    # Per-channel history, not the interleaved one: the graph runs once per modality per cycle,
    # so the last two entries of `affect_history` are usually the two channels disagreeing
    # inside a single cycle rather than one state holding across two -- which made the
    # consecutive-cycle condition effectively unsatisfiable. See profile_service.apply_affect.
    from app.services.profile_service import sustain_history

    allowed, reason = passes_adaptation_gate(
        state.get("affect_state"),
        state.get("affect_confidence"),
        sustain_history(profile or {}, state.get("affect_source")),
        cooldown_now,
        cooldown_last,
        state.get("affect_source"),
        config,
    )
    if not allowed:
        return False, reason

    # What is on the learner's screen. Only a cycle the DETECTOR would act on reaches this, and it
    # runs before the cap and the draw so a hold withholds from both trial arms alike.
    held = _screen_hold(state, profile or {})
    if held:
        return False, held

    # Checked BEFORE the draw, and counted across BOTH arms. Capping only DELIVERED interventions
    # would stop the delivered arm at six while the withheld arm carried on accruing controls --
    # the two would then cover different parts of the session, and later observations would appear
    # in one arm only. Counting eligibility instead makes both arms end together.
    if _session_cap_reached(profile or {}, state.get("session_id"), config):
        return False, GATE_SESSION_CAP

    # Applied LAST, and only to cycles that already cleared everything else, so the withheld set
    # is exactly the eligible set. Drawing earlier would withhold cycles that would have failed
    # the gate anyway, which would put unmatched cycles in the control arm and bias the contrast.
    rate = min(1.0, max(0.0, config.withhold_rate if config else ADAPT_WITHHOLD_RATE))
    if rate > 0.0 and withhold_draw(
        state.get("learner_id"), state.get("session_id"), state.get("cycle_number")
    ) < rate:
        return False, GATE_WITHHELD_RANDOM

    return True, GATE_OK


def _screen_hold(state: AgentState, profile: dict) -> str | None:
    """The delivery guard's verdict for this cycle, with the ladder position it needs."""
    import time

    from app.agents import delivery_guard

    ui = state.get("ui_state") or {}
    if not ui:
        return None
    section_id = (state.get("content_context") or {}).get("section_id")
    affect = state.get("affect_state")
    used = current_rung(profile, state.get("session_id"), section_id, affect)
    used = max(0, used - delivery_guard.rung_credit(ui, section_id, affect))
    return delivery_guard.blocked_reason(
        ui,
        now_ms=int(time.time() * 1000),
        section_id=section_id,
        affect_state=affect,
        rungs_used=used,
    )


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
