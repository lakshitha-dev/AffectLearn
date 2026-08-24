// Types for the observability dashboard (Monitor). Mirrors the backend monitor bus
// payloads (app/services/monitor_bus.py, trace.py) and the /monitor REST endpoints.

export type MonitorCategory = "domain" | "trace";
export type NodeKind = "active" | "stub";

/** The four affect categories, in the index order the models emit `probs`. */
export const AFFECT_LABELS = ["bored", "confused", "engaged", "frustrated"] as const;
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
  gateReasonsUnknown: Record<string, number>;
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
}
