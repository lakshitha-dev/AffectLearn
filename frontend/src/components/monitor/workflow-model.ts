/**
 * The Agent Workflow graph's MODEL: which cards and connectors to draw, what each one says, and
 * which route the last cycle took. Pure -- no React, no React Flow -- so every rule the graph
 * displays is testable without a canvas.
 *
 * Two sources are combined, and each answers a different question:
 *   - the live trace (`nodeStates`, `lastRoute`, from the SSE stream) says which nodes RAN and
 *     how long they took, but it only exists while the page is open;
 *   - the recorded cycle (`SessionCycle`, from the research record) says WHAT each step decided
 *     -- the affect, the gate verdict, the action -- and survives a reload.
 */

import { layeredLayout } from "@/lib/graph-layout";
import type {
  GraphTopology,
  MonitorHealth,
  NodeRuntimeState,
  NodeRuntimeStatus,
  RouteDecision,
  SessionCycle,
} from "@/types/monitor";

export type StepKind =
  | "trigger"
  | "sensing"
  | "condition"
  | "agent"
  | "subagent"
  | "output"
  | "log"
  | "end";

/** How a step fared in the cycle on screen. `skipped` = not on the route this cycle took. */
export type StepStatus = NodeRuntimeStatus | "skipped";

export interface StepData {
  id: string;
  kind: StepKind;
  eyebrow: string;
  title: string;
  detail: string;
  status: StepStatus;
  durationMs?: number;
  stub: boolean;
  desc: string;
  [key: string]: unknown;
}

export interface ServiceData {
  id: string;
  host: string;
  label: string;
  sublabel: string;
  /** true = healthy, false = down, null = no health signal for this service. */
  healthy: boolean | null;
  [key: string]: unknown;
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  taken: boolean;
}

export interface WorkflowModel {
  steps: (StepData & { position: { x: number; y: number } })[];
  services: (ServiceData & { position: { x: number; y: number } })[];
  edges: FlowEdge[];
  /** "adaptive" | "log_only" | null when nothing has run yet. */
  route: "adaptive" | "log_only" | null;
  hasActivity: boolean;
}

export const STEP_WIDTH = 240;
const GAP_X = 300;
const GAP_Y = 170;

const META: Record<string, { kind: StepKind; eyebrow: string; title: string }> = {
  START: { kind: "trigger", eyebrow: "Trigger", title: "Learner cycle" },
  affect_detection: { kind: "sensing", eyebrow: "Sensing", title: "Affect Detection" },
  learner_profiler: { kind: "condition", eyebrow: "Condition", title: "Adaptation gate" },
  log_only: { kind: "log", eyebrow: "Log", title: "Record only" },
  pedagogical: { kind: "agent", eyebrow: "Agent", title: "Pedagogical Agent" },
  content_adapter: { kind: "agent", eyebrow: "Agent", title: "Content Adapter" },
  video_resource: { kind: "subagent", eyebrow: "Sub-agent", title: "Video Sub-agent" },
  deliver: { kind: "output", eyebrow: "Output", title: "Deliver to learner" },
  END: { kind: "end", eyebrow: "End", title: "Cycle complete" },
};

const EDGE_LABELS: Record<string, string> = {
  "learner_profiler->pedagogical": "gate passed",
  "learner_profiler->log_only": "held back",
  "pedagogical->content_adapter": "writes the message",
  "pedagogical->video_resource": "delegates: show_video",
};

/** Gate reasons that let a cycle through to the agents. */
const PASSING = new Set(["ok", "learner_request"]);

type Rec = Record<string, unknown> | null | undefined;
const str = (v: unknown): string | undefined => (typeof v === "string" && v ? v : undefined);
const num = (v: unknown): number | undefined => (typeof v === "number" ? v : undefined);

function affectLine(cycle: SessionCycle | null): string | undefined {
  if (!cycle) return undefined;
  const channels = [cycle.facial as Rec, cycle.behavioural as Rec].filter(Boolean) as Record<
    string,
    unknown
  >[];
  // The reading the gate ruled on, else the most confident channel.
  const gateState = str(cycle.gate?.affect_state);
  const primary =
    channels.find((c) => str(c.affect_state) === gateState) ??
    [...channels].sort(
      (a, b) => (num(b.affect_confidence) ?? 0) - (num(a.affect_confidence) ?? 0),
    )[0];
  if (!primary) return undefined;
  const state = str(primary.affect_state) ?? "—";
  const conf = num(primary.affect_confidence);
  const source = str(primary.affect_source)?.replace("_model", "").replace("facial_", "");
  return [state, conf != null ? conf.toFixed(2) : null, source].filter(Boolean).join(" · ");
}

function detailFor(id: string, cycle: SessionCycle | null, route: WorkflowModel["route"]): string {
  const strat = cycle?.strategy as Rec;
  const trig = cycle?.triggered as Rec;
  const del = cycle?.delivered as Rec;
  const action = str(strat?.action_type);
  switch (id) {
    case "START":
      return "every 30 s · face + interaction signals";
    case "affect_detection":
      return affectLine(cycle) ?? "waiting for a reading";
    case "learner_profiler": {
      const reason = str(cycle?.gate?.reason);
      if (!reason) return "waiting for a verdict";
      if (reason === "learner_request") return "learner asked for help";
      return PASSING.has(reason) ? "gate passed" : `held back: ${reason.replace(/_/g, " ")}`;
    }
    case "log_only":
      return route === "log_only" ? "logged for research, no change" : "not needed this cycle";
    case "pedagogical":
      if (!action) return route === "adaptive" ? "deciding…" : "not reached";
      return `${action}${strat?.fallback ? " · rule fallback" : " · LLM"}`;
    case "content_adapter":
      if (!trig) return action ? "writing…" : "not reached";
      return trig.generated ? "message written by LLM" : trig.fallback ? "pre-written fallback" : "no text needed";
    case "video_resource":
      return action === "show_video" ? "finding one short video" : "idle · only for show_video";
    case "deliver":
      if (del) return `${str(del.action) ?? "adaptation"} sent`;
      return trig ? "not confirmed" : "nothing to send";
    case "END":
      return route === "adaptive" ? "help delivered" : route === "log_only" ? "recorded" : "—";
    default:
      return "";
  }
}

export interface BuildInput {
  topology: GraphTopology | undefined;
  nodeStates: Record<string, NodeRuntimeState>;
  lastRoute: RouteDecision | null;
  cycle: SessionCycle | null;
  health?: MonitorHealth;
}

export function buildWorkflow({
  topology,
  nodeStates,
  lastRoute,
  cycle,
  health,
}: BuildInput): WorkflowModel {
  const graphNodes = topology?.nodes ?? [];
  const graphEdges = topology?.edges ?? [];
  const ids = ["START", ...graphNodes.map((n) => n.id), "END"];
  const byId = new Map(graphNodes.map((n) => [n.id, n]));

  // Which route did the most recent cycle take? The live router decision wins; otherwise the
  // recorded gate verdict answers it.
  let route: WorkflowModel["route"] = null;
  if (lastRoute?.chosen) route = lastRoute.chosen === "pedagogical" ? "adaptive" : "log_only";
  else if (cycle?.gate?.reason) route = PASSING.has(cycle.gate.reason) ? "adaptive" : "log_only";

  const action = str((cycle?.strategy as Rec)?.action_type);
  const liveCycles = Object.values(nodeStates)
    .map((s) => s.lastCycle)
    .filter((c): c is number => typeof c === "number");
  const latestLive = liveCycles.length ? Math.max(...liveCycles) : null;

  const onRoute = (id: string): boolean => {
    if (!route) return false;
    if (id === "START" || id === "END" || id === "affect_detection" || id === "learner_profiler")
      return true;
    if (id === "log_only") return route === "log_only";
    if (id === "video_resource") return route === "adaptive" && action === "show_video";
    return route === "adaptive";
  };

  const statusFor = (id: string): StepStatus => {
    const live = nodeStates[id];
    if (live && (latestLive == null || live.lastCycle === latestLive)) {
      // The sub-agent node always RUNS (it no-ops unless the strategist chose show_video), so a
      // live "done" on a hint cycle would light it up for work it did not do.
      if (id === "video_resource" && action !== "show_video" && live.status === "done")
        return "skipped";
      return live.status;
    }
    if (!route) return "idle";
    return onRoute(id) ? "done" : "skipped";
  };

  const { positions } = layeredLayout(
    ids,
    [
      ...graphEdges,
      // The payload spells the sentinels START/END; keep them even if the server omits them.
      ...(graphEdges.some((e) => e.from === "START")
        ? []
        : [{ from: "START", to: graphNodes[0]?.id ?? "END" }]),
    ].map((e) => ({ from: e.from, to: e.to })),
    { gapX: GAP_X, gapY: GAP_Y },
  );

  const steps = ids.map((id) => {
    const meta = META[id] ?? {
      kind: "agent" as StepKind,
      eyebrow: "Agent",
      title: byId.get(id)?.label ?? id,
    };
    const status = statusFor(id);
    return {
      id,
      kind: meta.kind,
      eyebrow: meta.eyebrow,
      title: meta.title,
      detail: detailFor(id, cycle, route),
      status,
      durationMs: nodeStates[id]?.lastDurationMs,
      stub: byId.get(id)?.kind === "stub",
      desc: byId.get(id)?.desc ?? "",
      // The layout returns CENTRES; React Flow positions a node by its top-left corner.
      position: { x: positions[id].x - STEP_WIDTH / 2, y: positions[id].y },
    };
  });

  const stepStatus = new Map(steps.map((s) => [s.id, s.status]));
  const ran = (id: string) => {
    const s = stepStatus.get(id);
    return s === "done" || s === "running" || s === "error";
  };

  const edges: FlowEdge[] = graphEdges.map((e) => ({
    id: `${e.from}->${e.to}`,
    source: e.from,
    target: e.to,
    label: EDGE_LABELS[`${e.from}->${e.to}`],
    taken: ran(e.from) && ran(e.to),
  }));

  // External services each agent depends on, drawn as badges beside the node that calls them.
  const facialOk = health?.models.facial.available;
  const behaviouralOk = health?.models.behavioral.available;
  const llm = health?.llm;
  const serviceDefs: ServiceData[] = [
    {
      id: "svc-onnx",
      host: "affect_detection",
      label: "ONNX models",
      sublabel: "face geometry · behaviour",
      healthy: health ? Boolean(facialOk && behaviouralOk) : null,
    },
    {
      id: "svc-redis",
      host: "learner_profiler",
      label: "Redis",
      sublabel: "learner profile · gate state",
      healthy: health ? health.redis.enabled : null,
    },
    {
      id: "svc-llm",
      host: "pedagogical",
      label: llm?.model ? `LLM · ${llm.model}` : "LLM",
      sublabel: "strategist + content adapter",
      healthy: llm ? llm.reachable : null,
    },
    {
      id: "svc-youtube",
      host: "video_resource",
      label: "YouTube Data API",
      sublabel: "search · pick one video",
      healthy: null,
    },
  ];
  const services = serviceDefs
    .filter((s) => positions[s.host])
    .map((s) => ({
      ...s,
      position: { x: positions[s.host].x + STEP_WIDTH / 2 + 36, y: positions[s.host].y + 18 },
    }));

  const hasActivity = route != null || Object.keys(nodeStates).length > 0;
  return { steps, services, edges, route, hasActivity };
}
