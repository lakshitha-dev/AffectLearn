"""Conditional routing for the agent graph (Story 4.4).

Pure functions of `AgentState` (no I/O) so they are unit-testable in isolation.

Routing follows the architecture (lines 166-174): in Phase A (non-adaptive data
collection, FR28) or for the control group, the cycle goes to `log_only` and ENDs —
no adaptation. Only Phase B + adaptive group takes the pedagogical branch (Epic 5).
Until Story 6.1 wires real phase/group, `make_initial_state` defaults to
phase_a/control, so production routes to `log_only`.
"""

from app.agents.state import AgentState

# Conditional-edge route keys (graph node names).
ROUTE_LOG_ONLY = "log_only"
ROUTE_PEDAGOGICAL = "pedagogical"


def should_adapt(state: AgentState) -> bool:
    """True only on the Phase B / adaptive-group path."""
    return state.get("phase") == "phase_b" and state.get("group") == "adaptive"


def route_after_profiler(state: AgentState) -> str:
    """Map the adaptation decision to the next node key for the conditional edge."""
    return ROUTE_PEDAGOGICAL if should_adapt(state) else ROUTE_LOG_ONLY
