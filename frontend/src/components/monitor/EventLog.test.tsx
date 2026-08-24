/**
 * Tests for the live event log.
 *
 * The bug this guards: the summary guarded on `affect_state` but formatted `affect_confidence`,
 * so `learner_profile_updated` — which carries a state and has never carried a confidence —
 * rendered "engaged (NaN%)" on every single cycle. `undefined * 100` is `NaN`, and
 * `Math.round(NaN)` is `NaN`, so it printed straight into the UI.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { createElement } from "react";
import type { MonitorEvent } from "@/types/monitor";

vi.mock("recharts", () => ({}));

import { EventLog } from "./EventLog";

function ev(over: Partial<MonitorEvent> = {}): MonitorEvent {
  return {
    category: "domain",
    event_type: "behavioral_affect_detected",
    timestamp: 1_700_000_000_000,
    session_id: "s1",
    cycle_number: 1,
    ...over,
  } as MonitorEvent;
}

describe("EventLog summaries", () => {
  it("never renders NaN for an event with no confidence", () => {
    render(
      createElement(EventLog, {
        events: [
          ev({
            event_type: "learner_profile_updated",
            payload: { affect_state: "engaged", adaptation_gate: "state_not_actionable" },
          }),
        ],
      }),
    );
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });

  it("shows the gate reason for a profile update, which appears nowhere else live", () => {
    render(
      createElement(EventLog, {
        events: [
          ev({
            event_type: "learner_profile_updated",
            payload: { affect_state: "engaged", adaptation_gate: "low_confidence" },
          }),
        ],
      }),
    );
    expect(screen.getByText(/gate: low_confidence/)).toBeInTheDocument();
  });

  it("still shows a percentage when a real confidence is present", () => {
    render(
      createElement(EventLog, {
        events: [ev({ payload: { affect_state: "confused", affect_confidence: 0.72 } })],
      }),
    );
    expect(screen.getByText(/confused \(72%\)/)).toBeInTheDocument();
  });

  it("falls back to the bare state rather than a broken percentage", () => {
    render(
      createElement(EventLog, {
        events: [ev({ payload: { affect_state: "engaged" } })],
      }),
    );
    expect(screen.getByText("engaged")).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("surfaces a node_error message, which was colour-coded but never shown", () => {
    render(
      createElement(EventLog, {
        events: [
          ev({
            category: "trace",
            event_type: "node_error",
            node: "affect_detection",
            duration_ms: 12,
            error: "onnx session failed",
          }),
        ],
      }),
    );
    expect(screen.getByText(/onnx session failed/)).toBeInTheDocument();
  });

  it("includes the routing reason, not just the chosen route", () => {
    render(
      createElement(EventLog, {
        events: [
          ev({
            category: "trace",
            event_type: "route_decision",
            chosen: "log_only",
            reason: "gate withheld (cooldown)",
          }),
        ],
      }),
    );
    expect(screen.getByText(/log_only/)).toBeInTheDocument();
    expect(screen.getByText(/cooldown/)).toBeInTheDocument();
  });

  it("renders an empty summary without crashing on a payload-less event", () => {
    render(createElement(EventLog, { events: [ev({ event_type: "ws_connected" })] }));
    expect(screen.getByText("ws_connected")).toBeInTheDocument();
  });
});
