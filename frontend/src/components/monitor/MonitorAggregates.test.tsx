/**
 * Tests for the Aggregate tab.
 *
 * The point of this view is the gate-reason distribution and the fallback rate, so those are
 * what is asserted — plus the loading/error ladder and the "unknown reason" escape hatch.
 * `useMonitorAggregates` and recharts are mocked (recharts needs layout, which jsdom lacks).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import type { MonitorAggregates as Aggregates } from "@/types/monitor";

// recharts measures its container; in jsdom that is 0x0 and children never render.
vi.mock("recharts", () => {
  const Passthrough = ({ children }: { children?: ReactNode }) =>
    createElement("div", null, children);
  return {
    ResponsiveContainer: Passthrough,
    BarChart: Passthrough,
    Bar: Passthrough,
    Cell: () => null,
    CartesianGrid: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
    LabelList: () => null,
  };
});

const useMonitorAggregates = vi.fn();
const useMonitorHealth = vi.fn(() => ({ data: undefined }));
const exportMonitorCsv = vi.fn(async () => {});
vi.mock("@/hooks/use-monitor", () => ({
  useMonitorAggregates: (...a: unknown[]) => useMonitorAggregates(...a),
  useMonitorHealth: () => useMonitorHealth(),
  exportMonitorCsv: (...a: unknown[]) => exportMonitorCsv(...(a as [])),
}));

vi.mock("@/components/ui/select", () => ({
  Select: ({ children }: { children?: ReactNode }) => createElement("div", null, children),
  SelectTrigger: ({ children }: { children?: ReactNode }) =>
    createElement("button", null, children),
  SelectContent: ({ children }: { children?: ReactNode }) => createElement("div", null, children),
  SelectItem: ({ children }: { children?: ReactNode }) => createElement("div", null, children),
  SelectValue: () => null,
}));

import { MonitorAggregates } from "./MonitorAggregates";

function agg(over: Partial<Aggregates> = {}): Aggregates {
  return {
    windowHours: 24,
    startTs: 1,
    endTs: 2,
    totalEvents: 100,
    eventsByType: { learner_profile_updated: 60 },
    sessions: 3,
    cycles: 60,
    interventions: { delivered: 2, perHour: 0.083, fallback: 2, fallbackRate: 1.0 },
    gateReasons: {
      state_not_actionable: 40,
      low_confidence: 12,
      not_sustained: 5,
      cooldown: 3,
    },
    gateReasonsUnknown: {},
    gatedCycles: 60,
    affectCounts: { engaged: 40, confused: 20 },
    // The facial channel pinned below the gate is the shape the live pipeline produced while the
    // crop geometry was mismatched.
    modalityStats: {
      behavioral: { n: 40, min: 0.02, max: 0.72, mean: 0.21, overThreshold: 2, reachedThreshold: true },
      facial: { n: 40, min: 0.48, max: 0.55, mean: 0.51, overThreshold: 0, reachedThreshold: false },
      multimodal: { n: 0 },
    },
    adaptMinConfidence: 0.7,
    confidence: "high",
    insufficient_data: false,
    ...over,
  };
}

beforeEach(() => {
  useMonitorAggregates.mockReset();
  useMonitorHealth.mockReset();
  useMonitorHealth.mockReturnValue({ data: undefined } as never);
  exportMonitorCsv.mockReset();
});

describe("MonitorAggregates", () => {
  it("shows a skeleton with role=status while pending, not a spinner", () => {
    useMonitorAggregates.mockReturnValue({ isPending: true });
    render(createElement(MonitorAggregates));
    expect(screen.getByRole("status", { name: /loading aggregates/i })).toBeInTheDocument();
  });

  it("renders an inline error with Retry", () => {
    const refetch = vi.fn();
    useMonitorAggregates.mockReturnValue({
      isError: true,
      error: new Error("boom"),
      refetch,
    });
    render(createElement(MonitorAggregates));
    expect(screen.getByText(/aggregates unavailable: boom/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("surfaces a 100% fallback rate as the vLLM consequence", () => {
    useMonitorAggregates.mockReturnValue({ data: agg(), isPending: false });
    render(createElement(MonitorAggregates));
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText(/every adaptation was canned, not generated/i)).toBeInTheDocument();
  });

  it("shows a dash rather than 0% when nothing was delivered", () => {
    useMonitorAggregates.mockReturnValue({
      data: agg({
        interventions: { delivered: 0, perHour: 0, fallback: 0, fallbackRate: null },
      }),
      isPending: false,
    });
    render(createElement(MonitorAggregates));
    expect(screen.getByText(/no adaptations delivered yet/i)).toBeInTheDocument();
  });

  it("names the actionable states from live config rather than a hardcoded claim", () => {
    useMonitorAggregates.mockReturnValue({ data: agg(), isPending: false });
    useMonitorHealth.mockReturnValue({
      data: { models: { decision: { adaptStates: ["confused"], adaptMinConfidence: 0.7 } } },
    } as never);
    render(createElement(MonitorAggregates));
    // "confused" also appears in the detections panel, so scope the assertion to the caption.
    const caption = screen.getByText(/Actionable states are/i);
    expect(caption).toBeInTheDocument();
    expect(caption.textContent).toContain("confused");
  });

  it("degrades to a neutral sentence when the config has not loaded", () => {
    useMonitorAggregates.mockReturnValue({ data: agg(), isPending: false });
    useMonitorHealth.mockReturnValue({ data: undefined } as never);
    render(createElement(MonitorAggregates));
    expect(
      screen.getByText(/deployed models cannot emit never appears below/i),
    ).toBeInTheDocument();
  });

  it("flags an unrecognised gate reason instead of hiding it", () => {
    useMonitorAggregates.mockReturnValue({
      data: agg({ gateReasonsUnknown: { some_future_reason: 4 } }),
      isPending: false,
    });
    render(createElement(MonitorAggregates));
    expect(screen.getByText(/some_future_reason/)).toBeInTheDocument();
    expect(screen.getByText(/out of date with the backend/i)).toBeInTheDocument();
  });

  it("warns when the sample is too small to read proportions from", () => {
    useMonitorAggregates.mockReturnValue({
      data: agg({ insufficient_data: true, gatedCycles: 3 }),
      isPending: false,
    });
    render(createElement(MonitorAggregates));
    expect(screen.getByText(/limited data/i)).toBeInTheDocument();
  });

  it("renders an empty-window message rather than an empty chart", () => {
    useMonitorAggregates.mockReturnValue({
      data: agg({
        gateReasons: {
          state_not_actionable: 0,
          low_confidence: 0,
          not_sustained: 0,
          cooldown: 0,
        },
        affectCounts: {},
      }),
      isPending: false,
    });
    render(createElement(MonitorAggregates));
    expect(screen.getByText(/no gated cycles in this window yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no detections in this window/i)).toBeInTheDocument();
  });
});


describe("MonitorAggregates — measured verdicts and export", () => {
  it("flags a channel that never reached the gate, using measured values", () => {
    useMonitorAggregates.mockReturnValue({ data: agg(), isPending: false });
    render(createElement(MonitorAggregates));
    // facial: 0/40 over the gate, rendered as a ratio rather than a claim.
    expect(screen.getByText("0/40")).toBeInTheDocument();
    expect(screen.getByText("0.550")).toBeInTheDocument();
  });

  it("renders the event histogram that was previously collected and discarded", () => {
    useMonitorAggregates.mockReturnValue({ data: agg(), isPending: false });
    render(createElement(MonitorAggregates));
    expect(screen.getByText("Events by type")).toBeInTheDocument();
    expect(screen.getByText("learner_profile_updated")).toBeInTheDocument();
  });

  it("no longer asserts an invented operating point", () => {
    useMonitorAggregates.mockReturnValue({ data: agg(), isPending: false });
    render(createElement(MonitorAggregates));
    expect(screen.queryByText(/designed operating point/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/~1\.5/)).not.toBeInTheDocument();
  });

  it("exports the window currently on screen", async () => {
    useMonitorAggregates.mockReturnValue({ data: agg(), isPending: false });
    render(createElement(MonitorAggregates, { sessionId: "sess-1" }));
    const btn = screen.getByRole("button", { name: /export csv/i });
    btn.click();
    await vi.waitFor(() => expect(exportMonitorCsv).toHaveBeenCalledWith(24, "sess-1"));
  });
});
