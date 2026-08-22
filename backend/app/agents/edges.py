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

import os

from app.agents.state import AgentState

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
GATE_OK = "ok"
GATE_NOT_ELIGIBLE = "not_eligible"
GATE_NO_AFFECT = "no_affect"
GATE_STATE_NOT_ACTIONABLE = "state_not_actionable"
GATE_LOW_CONFIDENCE = "low_confidence"
GATE_NOT_SUSTAINED = "not_sustained"
GATE_COOLDOWN = "cooldown"


def should_adapt(state: AgentState) -> bool:
    """ELIGIBILITY only: True on the Phase B / adaptive-group path.

    Unchanged from Story 4.4 — the gate is applied on top of this, not instead of it, so the
    tri-modal phase/group contract and its tests are untouched.
    """
    return state.get("phase") == "phase_b" and state.get("group") == "adaptive"


def passes_adaptation_gate(
    affect_state: str | None,
    affect_confidence: float | None,
    affect_history: list | None,
    cycle_number: int | None,
    last_adaptation_cycle: int | None,
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

    if float(affect_confidence or 0.0) < ADAPT_MIN_CONFIDENCE:
        return False, GATE_LOW_CONFIDENCE

    need = max(1, ADAPT_MIN_CONSECUTIVE)
    recent = list(affect_history or [])[-need:]
    if len(recent) < need or any(a != affect_state for a in recent):
        return False, GATE_NOT_SUSTAINED

    if last_adaptation_cycle is not None and cycle_number is not None:
        if int(cycle_number) - int(last_adaptation_cycle) < ADAPT_COOLDOWN_CYCLES:
            return False, GATE_COOLDOWN

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
    return passes_adaptation_gate(
        state.get("affect_state"),
        state.get("affect_confidence"),
        (profile or {}).get("affect_history"),
        state.get("cycle_number"),
        last_adaptation_cycle,
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
