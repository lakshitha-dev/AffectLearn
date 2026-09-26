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
#: `performance_only` is not a modality in the sensing sense — no model ran. It is listed here
#: so a research event can be filtered to the channel that produced it, and so an analysis can
#: separate model-driven interventions from behaviour-driven ones without inferring it.
DETECTION_MODES: tuple[str, ...] = (
    "multimodal", "facial_only", "behavioral_only", "performance_only",
)
PHASES: tuple[str, ...] = ("phase_a", "phase_b")
GROUPS: tuple[str, ...] = ("adaptive", "control")

# Provenance markers for affect_source (Story 4.4 Decision; 4.4b adds behavioral).
AFFECT_SOURCE_CATEGORY = "category_model"
AFFECT_SOURCE_ENGAGEMENT = "engagement_adapter"
AFFECT_SOURCE_BEHAVIORAL = "behavioral_model"
AFFECT_SOURCE_FUSION = "fusion"  # late-fused facial + behavioral (Story 4.4c)

# Facial geometry: gaze, mouth openness and landmark motion, aggregated over a window and
# classified by a gradient-boosted model. Kept SEPARATE from AFFECT_SOURCE_CATEGORY because the
# two facial artifacts differ in every property the gate cares about — construct (disengagement
# vs confusion), corpus (EngageNet vs DAiSEE), measured precision at the deployed 0.70 floor
# (0.872 vs 0.500), and input (11 scalars per frame vs 96x96 pixels). Sharing one marker would
# make it impossible to grant one channel decisive authority without granting it to both.
AFFECT_SOURCE_FACIAL_GEOMETRY = "facial_geometry"

#: A struggle reading taken from what the learner DID -- wrong answers, revealing an answer,
#: going back to re-read, dwelling. Not a model: an openly-weighted count of observed behaviours.
#:
#: It exists because both trained channels are weak on THIS interface, and the code says so:
#: `section_features` records the behavioural model as "structurally blind on this UI" (two
#: scroll events per window, P(confused)=0.008 under deliberate confusion), and Chapter 4 records
#: the facial channel's live scores compressing into a 0.127-wide band. A gate that almost never
#: opens makes the adaptive arm of a study indistinguishable from the control.
AFFECT_SOURCE_PERFORMANCE = "performance"

#: The learner ASKED for more help ("Still stuck") or to move on ("I'd rather move on") from a card
#: already on screen. Not a detection: nothing is inferred, the learner said so. It therefore
#: bypasses the detection gate (confidence, persistence, cooldown), which exists to stop an
#: imperfect DETECTOR interrupting a learner, and does not apply to a learner who asked. It never
#: enters the randomised trial arms, so it cannot move any gate or trial statistic.
AFFECT_SOURCE_LEARNER_REQUEST = "learner_request"


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
    # The positive-class probability each binary channel's gate actually thresholds.
    #
    # `resolve_affect` returns these in its extras slot and `affect_detection` spreads them into
    # its state update -- but an undeclared key does not survive the graph, because this TypedDict
    # IS the state schema. They were therefore always None by the time ws.py read them off
    # `result_state`, so every event carried a null and the monitor rendered "—" for both
    # channels. The aggregate view looked correct only because it falls back to probs[1].
    #
    # Index 1 means a DIFFERENT construct per channel: P(confused) for the DAiSEE artifact,
    # P(disengaged) for the geometry one. They are separate keys for that reason.
    p_confused: float
    p_disengaged: float
    facial_inference: dict       # raw facial inference (engagement_level/label/confidence/probs/frames_used)
    behavioral_inference: dict   # raw behavioral inference (affect_index/label/confidence/probs/n_bins)
    empty_cycle: bool            # set when no face was detected the whole window
    #: The performance channel's weighted contributions and the raw counts behind them. Declared
    #: here because LangGraph merges only keys the state knows about — an undeclared key is
    #: silently dropped, and the breakdown is what lets an analyst recompute the score under
    #: different weights from the stored record rather than re-running the study.
    performance_breakdown: dict
    performance_counts: dict
    heuristic: bool              # set when the reading came from counts, not a model
    # Agent 2 — Learner Profiler output
    learner_profile: dict
    # Agent 3 — Pedagogical Strategist output
    strategy: dict | None
    # Agent 4 — Content Adapter output
    adaptation_content: dict | None
    # Agent 3's Video sub-agent output, set only when the strategist chose `show_video`: the
    # chosen video (`kind="embed"`), a search link (`kind="link"`), or `pending=True` when it did
    # not finish in its budget and the client should fetch it with the same brief.
    video_resource: dict | None
    # Terminal — `deliver` node output (Story 5.3). Transient deliver->WS-handler hand-off:
    # the built `adaptation` wire payload the socket-owning handler sends verbatim after
    # `ainvoke`. Not persisted; `make_initial_state` does not seed it (it is an output).
    delivery_message: dict | None
    # Control flags
    phase: str                   # one of PHASES
    group: str                   # one of GROUPS
    should_adapt: bool           # eligibility AND the adaptation gate (see agents.edges)
    adaptation_gate_reason: str  # GATE_* constant explaining the should_adapt decision
    # Which rung of this state's escalation ladder to use THIS cycle -- i.e. how many
    # interventions have already been delivered to this learner, in this section, for this state.
    # Computed by the profiler (the only node holding the fresh profile) and read by the
    # strategist. MUST be declared here: AgentState is the graph schema, and LangGraph silently
    # drops any key that is not, which is how p_confused/p_disengaged once vanished.
    ladder_rung: int
    # What a passing cycle will spend IF its card reaches the learner: the cooldown, the session
    # cap and a ladder rung for a detector-driven card, a rung only for a learner request. Set by
    # the profiler (`edges.pending_offer`) and applied by the socket handler after a successful
    # send (`learner_profiler.commit_delivered_offer`). None when the cycle spends nothing.
    # Declared for the same reason as `ladder_rung`: an undeclared key is dropped by LangGraph.
    offer_commit: dict | None
    # Transient per-cycle input (NOT persisted — see module docstring)
    facial_payload: dict
    behavioral_payload: dict
    #: Per-section struggle counters accumulated by the client. Transient like the others.
    performance_payload: dict
    # Late-fusion counterpart (Story 4.4c, decision path). The two modalities arrive on
    # SEPARATE WebSocket messages at independent cadences, so a cycle only ever carries one
    # payload. To fuse into the LIVE decision the handler passes the counterpart's already
    # computed inference result from `fusion_buffer` — the other model is NOT re-run, which
    # is what makes this late fusion rather than a second forward pass.
    counterpart_inference: dict   # the opposite modality's recent result, or {} if unpaired
    counterpart_modality: str     # "facial" | "behavioral" — which modality that result is
    fusion_applied: bool          # True when affect_state came from fuse_modalities
    fusion_weights: dict          # per-modality weights used, for the research event
    db: Any              # transient WS-connection AsyncSession for the profiler cold store (Story 4.5)
    content_context: dict  # transient: current section topic/difficulty for the strategist (Story 5.1)
    # transient: what is on the learner's screen (open card, section entry, visibility...), read by
    # the delivery guard. Loaded per cycle by the WS handler; see `agents/delivery_guard.py`.
    ui_state: dict


def make_initial_state(
    *,
    learner_id: str,
    session_id: str,
    cycle_number: int,
    facial_payload: dict[str, Any] | None = None,
    behavioral_payload: dict[str, Any] | None = None,
    performance_payload: dict[str, Any] | None = None,
    counterpart_inference: dict[str, Any] | None = None,
    counterpart_modality: str = "",
    db: Any = None,
    content_context: dict[str, Any] | None = None,
    phase: str = "phase_a",
    group: str = "control",
    ui_state: dict[str, Any] | None = None,
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
        performance_payload=performance_payload or {},
        counterpart_inference=counterpart_inference or {},
        counterpart_modality=counterpart_modality,
        db=db,
        content_context=content_context or {},
        ui_state=ui_state or {},
    )
