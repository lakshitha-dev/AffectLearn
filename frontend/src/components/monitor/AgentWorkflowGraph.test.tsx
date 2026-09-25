import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { buildWorkflow } from "./workflow-model";
import { WorkflowStepCard, ServiceBadgeCard } from "./WorkflowNode";
import type { GraphTopology, MonitorHealth, SessionCycle } from "@/types/monitor";

const TOPOLOGY: GraphTopology = {
  nodes: [
    { id: "affect_detection", label: "Affect Detection", kind: "active", desc: "ONNX" },
    { id: "learner_profiler", label: "Learner Profiler", kind: "active", desc: "gate" },
    { id: "log_only", label: "Log only", kind: "active", desc: "" },
    { id: "pedagogical", label: "Pedagogical", kind: "active", desc: "LLM" },
    { id: "content_adapter", label: "Content Adapter", kind: "active", desc: "" },
    { id: "video_resource", label: "Video Sub-agent", kind: "active", desc: "" },
    { id: "deliver", label: "Deliver", kind: "active", desc: "" },
  ],
  edges: [
    { from: "START", to: "affect_detection" },
    { from: "affect_detection", to: "learner_profiler" },
    { from: "learner_profiler", to: "log_only", kind: "conditional", route: "log_only" },
    { from: "learner_profiler", to: "pedagogical", kind: "conditional", route: "pedagogical" },
    { from: "pedagogical", to: "content_adapter" },
    { from: "pedagogical", to: "video_resource" },
    { from: "content_adapter", to: "deliver" },
    { from: "video_resource", to: "deliver" },
    { from: "deliver", to: "END" },
    { from: "log_only", to: "END" },
  ],
};

function cycle(overrides: Partial<SessionCycle> = {}): SessionCycle {
  return {
    cycle_number: 7,
    started_at: 1,
    facial: { affect_state: "bored", affect_confidence: 0.93, affect_source: "facial_geometry" },
    behavioural: { affect_state: "engaged", affect_confidence: 0.4 },
    fused: null,
    gate: { reason: "ok", affect_state: "bored" },
    strategy: { action_type: "increase_difficulty", fallback: false },
    triggered: { generated: true },
    delivered: { action: "increase_difficulty" },
    ...overrides,
  };
}

const step = (m: ReturnType<typeof buildWorkflow>, id: string) => m.steps.find((s) => s.id === id)!;
const edge = (m: ReturnType<typeof buildWorkflow>, id: string) => m.edges.find((e) => e.id === id)!;

describe("buildWorkflow", () => {
  it("draws every graph node plus the trigger and end, from the graph's own edges", () => {
    const m = buildWorkflow({ topology: TOPOLOGY, nodeStates: {}, lastRoute: null, cycle: null });
    expect(m.steps.map((s) => s.id)).toEqual([
      "START", "affect_detection", "learner_profiler", "log_only", "pedagogical",
      "content_adapter", "video_resource", "deliver", "END",
    ]);
    expect(m.edges).toHaveLength(10);
    expect(m.hasActivity).toBe(false);
    expect(m.route).toBeNull();
  });

  it("lights the adaptive route of a passed gate and fades the log-only branch", () => {
    const m = buildWorkflow({ topology: TOPOLOGY, nodeStates: {}, lastRoute: null, cycle: cycle() });
    expect(m.route).toBe("adaptive");
    expect(edge(m, "learner_profiler->pedagogical").taken).toBe(true);
    expect(edge(m, "learner_profiler->log_only").taken).toBe(false);
    expect(step(m, "log_only").status).toBe("skipped");
    expect(step(m, "affect_detection").detail).toBe("bored · 0.93 · geometry");
    expect(step(m, "pedagogical").detail).toBe("increase_difficulty · LLM");
    // The sub-agent only works on show_video; a hint cycle leaves it off the route.
    expect(step(m, "video_resource").status).toBe("skipped");
    expect(edge(m, "pedagogical->video_resource").taken).toBe(false);
  });

  it("puts the Video sub-agent on the route for show_video", () => {
    const m = buildWorkflow({
      topology: TOPOLOGY,
      nodeStates: {},
      lastRoute: null,
      cycle: cycle({ strategy: { action_type: "show_video" } }),
    });
    expect(step(m, "video_resource").status).toBe("done");
    expect(edge(m, "pedagogical->video_resource").taken).toBe(true);
    expect(edge(m, "video_resource->deliver").taken).toBe(true);
  });

  it("follows a withheld gate down the log-only branch", () => {
    const m = buildWorkflow({
      topology: TOPOLOGY,
      nodeStates: {},
      lastRoute: null,
      cycle: cycle({ gate: { reason: "cooldown" }, strategy: null, triggered: null, delivered: null }),
    });
    expect(m.route).toBe("log_only");
    expect(step(m, "learner_profiler").detail).toBe("held back: cooldown");
    expect(edge(m, "learner_profiler->log_only").taken).toBe(true);
    expect(step(m, "pedagogical").status).toBe("skipped");
  });

  it("prefers live trace status and the live router over the recorded cycle", () => {
    const m = buildWorkflow({
      topology: TOPOLOGY,
      nodeStates: {
        affect_detection: { status: "done", lastDurationMs: 12, lastCycle: 9 },
        learner_profiler: { status: "running", lastCycle: 9 },
      },
      lastRoute: { chosen: "log_only", t: 1 },
      cycle: cycle(),
    });
    expect(m.route).toBe("log_only");
    expect(step(m, "affect_detection").status).toBe("done");
    expect(step(m, "affect_detection").durationMs).toBe(12);
    expect(step(m, "learner_profiler").status).toBe("running");
  });

  it("attaches service badges with health from the monitor health payload", () => {
    const health = {
      models: {
        facial: { available: true },
        behavioral: { available: true },
      },
      llm: { endpoint: "e", model: "gpt-4o", reachable: false, adaptationsGenerated: false },
      redis: { enabled: true },
      database: { ok: true },
      websocket: { active_connections: 0 },
      monitor: { subscribers: 0, buffered_events: 0 },
    } as unknown as MonitorHealth;
    const m = buildWorkflow({ topology: TOPOLOGY, nodeStates: {}, lastRoute: null, cycle: null, health });
    const byId = Object.fromEntries(m.services.map((s) => [s.id, s]));
    expect(byId["svc-onnx"].healthy).toBe(true);
    expect(byId["svc-redis"].healthy).toBe(true);
    expect(byId["svc-llm"].label).toBe("LLM · gpt-4o");
    expect(byId["svc-llm"].healthy).toBe(false);
    expect(byId["svc-youtube"].healthy).toBeNull();
  });
});

describe("WorkflowStepCard", () => {
  it("names the step, its type and its status for assistive tech", () => {
    const m = buildWorkflow({ topology: TOPOLOGY, nodeStates: {}, lastRoute: null, cycle: cycle() });
    render(<WorkflowStepCard data={step(m, "pedagogical")} />);
    expect(screen.getByRole("group", { name: "Pedagogical Agent: done" })).toBeInTheDocument();
    expect(screen.getByText("Agent")).toBeInTheDocument();
    expect(screen.getByText("increase_difficulty · LLM")).toBeInTheDocument();
  });

  it("marks a skipped branch", () => {
    const m = buildWorkflow({ topology: TOPOLOGY, nodeStates: {}, lastRoute: null, cycle: cycle() });
    render(<WorkflowStepCard data={step(m, "log_only")} />);
    expect(screen.getByRole("group", { name: "Record only: not on this route" })).toHaveAttribute(
      "data-status",
      "skipped",
    );
  });

  it("renders a service badge with its health state", () => {
    render(
      <ServiceBadgeCard
        data={{ id: "s", host: "h", label: "Redis", sublabel: "profile", healthy: true }}
      />,
    );
    expect(screen.getByRole("note", { name: "Redis: healthy" })).toBeInTheDocument();
  });
});
