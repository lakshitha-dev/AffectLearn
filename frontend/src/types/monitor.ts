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
export interface MonitorHealth {
  models: {
    behavioral: { path: string; available: boolean };
    facial: { path: string; available: boolean };
  };
  redis: { enabled: boolean };
  database: { ok: boolean };
  websocket: { active_connections: number };
  monitor: { subscribers: number; buffered_events: number };
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
