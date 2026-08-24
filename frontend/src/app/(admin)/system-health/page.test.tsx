/**
 * Tests for the rewritten System Health page.
 *
 * The version this replaced was a hardcoded array that rendered "6/6 operational" and invented
 * uptime figures no matter what the system was doing — including while vLLM was unreachable in
 * production. The regression that matters is therefore: an unhealthy component must actually
 * show as unhealthy, and the vLLM consequence must be spelled out.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { createElement } from "react";
import type { MonitorHealth } from "@/types/monitor";

const useMonitorHealth = vi.fn();
vi.mock("@/hooks/use-monitor", () => ({
  useMonitorHealth: () => useMonitorHealth(),
}));

import SystemHealthPage from "./page";

function health(over: Partial<MonitorHealth> = {}): MonitorHealth {
  return {
    models: {
      behavioral: {
        path: "models/behavioral_confusion_gbdt.onnx",
        exists: true,
        available: true,
        kind: "aggregate",
        inputs: [{ name: "features", shape: [null, 80] }],
        outputs: [{ name: "probabilities", shape: [null, 2] }],
      },
      facial: {
        path: "models/cnn_lstm_confusion_anycut.onnx",
        exists: true,
        available: true,
        kind: "binary_confusion",
        inputs: [{ name: "clip", shape: ["batch", 16, 3, 96, 96] }],
        outputs: [{ name: "logits", shape: ["batch", 2] }],
      },
      decision: {
        adaptStates: ["confused"],
        adaptMinConfidence: 0.7,
        adaptMinConsecutive: 2,
        adaptCooldownCycles: 3,
        fusionDrivesDecision: true,
        forcedMode: "auto",
      },
    },
    llm: {
      endpoint: "http://vllm:8080",
      model: "affectlearn/llama-3-8b-pedagogical",
      reachable: false,
      adaptationsGenerated: false,
      error: "ConnectError: name resolution failed",
    },
    redis: { enabled: true },
    database: { ok: true },
    websocket: { active_connections: 1 },
    monitor: { subscribers: 1, buffered_events: 42 },
    ...over,
  };
}

beforeEach(() => {
  useMonitorHealth.mockReset();
});

describe("SystemHealthPage", () => {
  it("shows a skeleton with role=status while pending", () => {
    useMonitorHealth.mockReturnValue({ isPending: true });
    render(createElement(SystemHealthPage));
    expect(screen.getByRole("status", { name: /loading system health/i })).toBeInTheDocument();
  });

  it("renders an error with Retry when health cannot be read", () => {
    useMonitorHealth.mockReturnValue({ isError: true, error: new Error("nope"), refetch: vi.fn() });
    render(createElement(SystemHealthPage));
    expect(screen.getByText(/health unavailable: nope/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("counts an unreachable vLLM as unhealthy instead of reporting all-green", () => {
    useMonitorHealth.mockReturnValue({ data: health(), isPending: false });
    render(createElement(SystemHealthPage));
    // 5 checks, vLLM down -> 4/5, NOT 5/5.
    expect(screen.getByText(/4\/5 components healthy/i)).toBeInTheDocument();
  });

  it("states the consequence of an unreachable vLLM in plain terms", () => {
    useMonitorHealth.mockReturnValue({ data: health(), isPending: false });
    render(createElement(SystemHealthPage));
    expect(
      screen.getByText(/adaptations are served from the deterministic rule-based fallback/i),
    ).toBeInTheDocument();
  });

  it("reports all healthy when every component is up", () => {
    useMonitorHealth.mockReturnValue({
      data: health({
        llm: {
          endpoint: "http://vllm:8080",
          model: "m",
          reachable: true,
          adaptationsGenerated: true,
        },
      }),
      isPending: false,
    });
    render(createElement(SystemHealthPage));
    expect(screen.getByText(/5\/5 components healthy/i)).toBeInTheDocument();
  });

  it("shows resolved model kinds, so a path/kind mismatch is visible", () => {
    useMonitorHealth.mockReturnValue({ data: health(), isPending: false });
    render(createElement(SystemHealthPage));
    expect(screen.getByText(/aggregate/)).toBeInTheDocument();
    expect(screen.getByText(/binary_confusion/)).toBeInTheDocument();
  });

  it("shows a missing facial model as unavailable", () => {
    const h = health();
    h.models.facial = { path: "models/x.onnx", exists: false, available: false };
    useMonitorHealth.mockReturnValue({ data: h, isPending: false });
    render(createElement(SystemHealthPage));
    expect(screen.getAllByText(/unavailable/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/degrades to behavioural-only when absent/i)).toBeInTheDocument();
  });

  it("surfaces the gate configuration", () => {
    useMonitorHealth.mockReturnValue({ data: health(), isPending: false });
    render(createElement(SystemHealthPage));
    expect(screen.getByText(/adaptation gate configuration/i)).toBeInTheDocument();
    expect(screen.getByText("0.7")).toBeInTheDocument();
    expect(screen.getByText("confused")).toBeInTheDocument();
  });

  it("does not invent uptime or latency figures", () => {
    useMonitorHealth.mockReturnValue({ data: health(), isPending: false });
    render(createElement(SystemHealthPage));
    expect(screen.queryByText(/99\.9/)).not.toBeInTheDocument();
    expect(screen.getByText(/uptime and latency are not/i)).toBeInTheDocument();
  });
});
