// Types for the observability dashboard (Monitor). Mirrors the backend monitor bus
// payloads (app/services/monitor_bus.py, trace.py) and the /monitor REST endpoints.

export type MonitorCategory = "domain" | "trace";
export type NodeKind = "active" | "stub";

/** The four affect categories, in the index order the models emit `probs`. */
export const AFFECT_LABELS = ["bored", "confused", "engaged", "frustrated"] as const;

/**
 * One cycle's face-presence measurement.
 *
 * `seen` is frames containing a real detected face; `captured` is total frames in the cycle.
 * They diverged once faceless frames became centre crops instead of drops, which is exactly why
 * presence needs reporting rather than being inferred from `captured`.
 */
export interface FacePresencePoint {
  t: number;
  cycle: number | null;
  seen: number;
  captured: number;
  ratio: number;
  /** True when too few frames had a face for the cycle to describe a present learner. */
  absent: boolean;
}
export type AffectLabel = (typeof AFFECT_LABELS)[number];

export interface MonitorEventBase {
  category: MonitorCategory;
  event_type: string;
  timestamp: number;
  session_id?: string | null;
  learner_id?: string | null;
  cycle_number?: number | null;
  sequence_number?: number;
}

// A monitor event is the base plus arbitrary type-specific fields/payload.
export type MonitorEvent = MonitorEventBase & Record<string, unknown>;

// --- Graph topology (/monitor/graph) ---
export interface GraphNode {
  id: string;
  label: string;
  kind: NodeKind;
  desc: string;
}
export interface GraphEdge {
  from: string;
  to: string;
  kind?: string;
  route?: string;
}
export interface GraphTopology {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// --- Health (/monitor/health) ---

/** One ONNX input or output as reported by the server. Shape entries may be named dims. */
export interface OnnxIo {
  name: string;
  shape: (number | string | null)[];
}

/**
 * A resolved model artifact. `kind` is how the CODE will interpret the file, which is the
 * field that catches a path/kind mismatch (e.g. `binary_confusion` pointed at a 4-class
 * artifact produces confident nonsense rather than an error).
 */
export interface ModelReport {
  path: string;
  exists?: boolean;
  /** Kept for the existing MetricsBar contract; mirrors `exists`. */
  available: boolean;
  kind?: string;
  inputs?: OnnxIo[];
  outputs?: OnnxIo[];
  error?: string;
}

/** The gate + fusion configuration that turns a detection into an intervention. */
export interface DecisionReport {
  adaptStates?: string[];
  adaptMinConfidence?: number;
  /**
   * Per-channel confidence floors, keyed by affect_source.
   *
   * `adaptMinConfidence` is the global default and misdescribes any channel with an override —
   * the geometry channel gates at 0.70 while the global sits at 0.50 — so the header and the
   * System Health tile were both reporting a threshold that channel never uses.
   */
  channelMinConfidence?: Record<string, number>;
  /** Which channels may trigger an intervention alone. Returned by the API but never rendered. */
  decisiveAffectSources?: string[];
  adaptMinConsecutive?: number;
  adaptCooldownCycles?: number;
  fusionDrivesDecision?: boolean;
  forcedMode?: string;
  error?: string;
}

/**
 * vLLM reachability. When `reachable` is false, adaptations are served from the
 * deterministic rule-based fallback rather than generated.
 */
export interface LlmHealth {
  endpoint: string;
  model: string;
  reachable: boolean;
  adaptationsGenerated: boolean;
  status?: number;
  error?: string;
}

export interface MonitorHealth {
  models: {
    behavioral: ModelReport;
    facial: ModelReport;
    decision?: DecisionReport;
  };
  llm?: LlmHealth;
  redis: { enabled: boolean };
  database: { ok: boolean };
  websocket: { active_connections: number };
  monitor: { subscribers: number; buffered_events: number };
}

// --- Aggregates (/monitor/aggregates) ---

/**
 * Pipeline behaviour over a window. The gate-reason distribution is the point: at a 0.70
 * threshold most cycles are withheld, and the breakdown is how you tell a correctly
 * conservative gate from a mis-tuned one.
 */
export interface MonitorAggregates {
  windowHours: number;
  startTs: number;
  endTs: number;
  totalEvents: number;
  eventsByType: Record<string, number>;
  sessions: number;
  cycles: number;
  interventions: {
    delivered: number;
    perHour: number;
    fallback: number;
    /** null when nothing was delivered (avoids a 0/0). 1.0 means none were generated. */
    fallbackRate: number | null;
  };
  gateReasons: Record<string, number>;
  /**
   * Per-modality confidence distribution over the window.
   *
   * `reachedThreshold` is the operationally important field: a channel whose observed max never
   * crossed the gate cannot have driven an intervention, whatever its held-out AUC says. It is
   * measured per window, so it stops being reported the moment the channel starts crossing.
   */
  modalityStats: Record<
    string,
    {
      n: number;
      min?: number;
      max?: number;
      mean?: number;
      overThreshold?: number;
      reachedThreshold?: boolean;
    }
  >;
  /** The live gate threshold the stats above were compared against. */
  adaptMinConfidence: number | null;
  gateReasonsUnknown: Record<string, number>;
  /** Cycles that PASSED the gate. Not a withholding reason, so not a bar.
   *  Optional because the two App Services deploy in parallel and this client can
   *  briefly be newer than the API it is talking to. */
  gatePassed?: number;
  gatedCycles: number;
  affectCounts: Record<string, number>;
  confidence: "low" | "medium" | "high";
  insufficient_data: boolean;
}

// --- Sessions (/monitor/sessions) ---
export interface MonitorSessions {
  active: { user_id: string; session_id: string | null }[];
  recent_session_ids: string[];
}

// --- Derived (computed client-side in use-monitor-stream) ---
export type NodeRuntimeStatus = "idle" | "running" | "done" | "error";
export interface NodeRuntimeState {
  status: NodeRuntimeStatus;
  kind?: NodeKind;
  lastDurationMs?: number;
  lastCycle?: number | null;
}

export interface AffectPoint {
  t: number;
  cycle?: number | null;
  affect: string;
  confidence: number;
  source?: string;
  mode?: string;
}

export interface RouteDecision {
  chosen: string;
  phase?: string;
  group?: string;
  reason?: string;
  cycle?: number | null;
  t: number;
}

export interface MonitorMetrics {
  total: number;
  domainCount: number;
  traceCount: number;
  eventsPerSec: number;
  cyclesObserved: number;
  avgNodeMs: number | null;
  /** Latest cycle's face ratio, or null when no facial cycle has reported presence yet. */
  faceRatio: number | null;
  /** Latest cycle's presence verdict. null when unknown (no facial cycle, or a legacy event). */
  facePresent: boolean | null;
  /**
   * Whether a LEARNER session is currently producing cycles -- distinct from whether this
   * admin page is connected to the backend. The two were previously conflated: the header
   * read "Stream: live" and "Face: present 100%" whenever the page was open, because both
   * were derived from the admin SSE connection and the last event ever received. A closed
   * camera and an ended session therefore rendered identically to an active learner.
   *
   *   active  cycles arriving within STALE_AFTER_MS
   *   stale   no cycle for longer than that, but no explicit disconnect seen
   *   ended   `ws_disconnected` observed after the last cycle
   *   idle    nothing observed yet this page-load
   */
  sessionState: "active" | "stale" | "ended" | "idle";
  /** Epoch ms of the most recent cycle-bearing event; null when none seen. */
  lastCycleAt: number | null;
  /** Age of that event in ms, so panels can label values instead of implying they are current. */
  lastCycleAgeMs: number | null;
}

/* ── Session history (GET /monitor/session/{id}) ─────────────────────────────────────
 *
 * The DATABASE-backed view of a session, as opposed to `useMonitorStream`'s live ring buffer.
 * Fields mirror `session_history_service` exactly; anything the backend does not record is absent
 * here too rather than defaulted, so the UI can distinguish "not recorded" from "zero".
 */

/** One cycle, with both channels and the agent chain joined on cycle_number. */
export interface SessionCycle {
  cycle_number: number;
  started_at: number | null;
  /** `facial_affect_detected` payload, or null when that channel did not report. */
  facial: Record<string, unknown> | null;
  behavioural: Record<string, unknown> | null;
  /** Present only when both channels paired within the fusion window. */
  fused: Record<string, unknown> | null;
  gate: {
    reason?: string | null;
    affect_state?: string | null;
    /** Absent on rows written before provenance was recorded. */
    affect_source?: string | null;
    timestamp?: number;
  } | null;
  strategy: Record<string, unknown> | null;
  triggered: Record<string, unknown> | null;
  delivered: Record<string, unknown> | null;
}

/**
 * A transition between resolved states. DERIVED, not recorded — the system stores a state per
 * cycle and never a duration.
 */
export interface StateChange {
  at: number | null;
  cycle_number: number | null;
  /** null on the first run, and on any run that follows an observation gap. */
  from: string | null;
  to: string;
  confidence: number | null;
  source: string | null;
  /** null while the run is still open (the session may not have ended). */
  durationMs: number | null;
  /** Consecutive cycles this run covered — the quantity the gate's persistence rule counts. */
  cycles: number;
}

export interface SessionIntervention {
  cycle_number: number;
  detection: { state: string | null; confidence: number | null; source: string | null };
  gate: SessionCycle["gate"];
  strategy: Record<string, unknown> | null;
  triggered: Record<string, unknown> | null;
  delivered: Record<string, unknown> | null;
  /** Present only when a send actually failed; absent means "no failure recorded", not "fine". */
  deliveryFailed: Record<string, unknown> | null;
  /** The learner's response, joined by the server-issued adaptation_id. */
  response: Record<string, unknown> | null;
  /**
   * The next cycle that detected anything. SEQUENCE, NOT EFFECT — nothing in the record links an
   * intervention to a later state, so this must never be rendered as an outcome.
   */
  nextState: {
    cycle_number: number;
    state: string;
    confidence: number | null;
    source: string | null;
    at: number | null;
  } | null;
  /** Parts of the chain the backend does not record, named so the UI can say why. */
  missing: string[];
}

export interface SessionSummary {
  sessionId: string;
  startedAt: number | null;
  endedAt: number | null;
  durationMs: number | null;
  cycleCount: number;
  /** Cycles that actually resolved to a state — an empty cycle is not a detection. */
  detectionCount: number;
  stateChangeCount: number;
  interventionsTriggered: number;
  interventionsDelivered: number;
  /** Triggered without a matching delivery: the only signal a delivery failed. */
  deliveriesUnaccounted: number;
  meanConfidence: number | null;
  byState: Record<string, number>;
  dwellMsByState: Record<string, number>;
  selfReports: number;
}

export interface SessionHistory {
  sessionId: string;
  found: boolean;
  cycles: SessionCycle[];
  stateChanges: StateChange[];
  interventions: SessionIntervention[];
  /** Session-level: cycle_number is 0 on these events, so they cannot be joined to a hint. */
  interactions: Record<string, unknown>[];
  selfReports: Record<string, unknown>[];
  summary: SessionSummary | null;
}
