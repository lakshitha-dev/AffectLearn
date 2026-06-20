"""Shared agent state for the LangGraph 4-agent loop (Story 4.4).

`AgentState` is the SINGLE SOURCE OF TRUTH passed between every node — no side
channels (architecture lines 574-598, 1217). It is declared `total=False` because
one 30-second cycle fills fields progressively: the affect-detection node writes
the affect fields first; the profiler writes `learner_profile`/`should_adapt`; the
Phase B branch writes `strategy`/`adaptation_content` only when adaptation runs.
A non-total TypedDict models "not written yet" without forcing every node to fill
every key.

Label space (see Story 4.4 Dev Notes — Decision): `affect_state` is ALWAYS one of
the four affect CATEGORIES. Engagement intensity levels never reach this field; the
affect-detection node converts them via `affect_mapping` before writing here.

Privacy (NFR10): `facial_payload` carries the per-cycle facial input (incl. base64
frames). It is seeded into the in-memory state for one `ainvoke` and discarded — it
is never persisted (no checkpointer) and never logged. Do not add a LangGraph
checkpointer without first excluding this field.
"""

from __future__ import annotations

from typing import Any, TypedDict

# ── locked value sets (single source of truth for nodes + tests) ───────────────
AFFECT_STATES: tuple[str, ...] = ("bored", "confused", "engaged", "frustrated")
DETECTION_MODES: tuple[str, ...] = ("multimodal", "facial_only", "behavioral_only")
PHASES: tuple[str, ...] = ("phase_a", "phase_b")
GROUPS: tuple[str, ...] = ("adaptive", "control")

# Provenance markers for affect_source (Story 4.4 Decision; 4.4b adds behavioral).
AFFECT_SOURCE_CATEGORY = "category_model"
AFFECT_SOURCE_ENGAGEMENT = "engagement_adapter"
AFFECT_SOURCE_BEHAVIORAL = "behavioral_model"
AFFECT_SOURCE_FUSION = "fusion"  # late-fused facial + behavioral (Story 4.4c)


class AgentState(TypedDict, total=False):
    # Identifiers
    learner_id: str
    session_id: str
    cycle_number: int
    # Agent 1 — Affect Detection output
    affect_state: str            # one of AFFECT_STATES
    affect_confidence: float
    detection_mode: str          # one of DETECTION_MODES
    affect_source: str           # AFFECT_SOURCE_CATEGORY | AFFECT_SOURCE_ENGAGEMENT | AFFECT_SOURCE_BEHAVIORAL
    engagement_level: int        # additive: only when affect_source == engagement_adapter
    engagement_label: str        # additive: raw engagement label under the adapter
    facial_inference: dict       # raw facial inference (engagement_level/label/confidence/probs/frames_used)
    behavioral_inference: dict   # raw behavioral inference (affect_index/label/confidence/probs/n_bins)
    empty_cycle: bool            # set when no face was detected the whole window
    # Agent 2 — Learner Profiler output
    learner_profile: dict
    # Agent 3 — Pedagogical Strategist output
    strategy: dict | None
    # Agent 4 — Content Adapter output
    adaptation_content: dict | None
    # Terminal — `deliver` node output (Story 5.3). Transient deliver->WS-handler hand-off:
    # the built `adaptation` wire payload the socket-owning handler sends verbatim after
    # `ainvoke`. Not persisted; `make_initial_state` does not seed it (it is an output).
    delivery_message: dict | None
    # Control flags
    phase: str                   # one of PHASES
    group: str                   # one of GROUPS
    should_adapt: bool
    # Transient per-cycle input (NOT persisted — see module docstring)
    facial_payload: dict
    behavioral_payload: dict
    db: Any              # transient WS-connection AsyncSession for the profiler cold store (Story 4.5)
    content_context: dict  # transient: current section topic/difficulty for the strategist (Story 5.1)


def make_initial_state(
    *,
    learner_id: str,
    session_id: str,
    cycle_number: int,
    facial_payload: dict[str, Any] | None = None,
    behavioral_payload: dict[str, Any] | None = None,
    db: Any = None,
    content_context: dict[str, Any] | None = None,
    phase: str = "phase_a",
    group: str = "control",
) -> AgentState:
    """Seed an AgentState for one cycle.

    Exactly one modality payload is normally present per cycle: `facial_payload` for a
    `facial_features` message (Story 4.4) or `behavioral_payload` for a `behavioral_window`
    message (Story 4.4b). Both are transient (never persisted — see module docstring).

    Defaults to Phase A / control (the non-adaptive logging path) until Story 6.1 wires
    real A/B group + phase assignment.
    """
    return AgentState(
        learner_id=learner_id,
        session_id=session_id,
        cycle_number=cycle_number,
        phase=phase,
        group=group,
        facial_payload=facial_payload or {},
        behavioral_payload=behavioral_payload or {},
        db=db,
        content_context=content_context or {},
    )
