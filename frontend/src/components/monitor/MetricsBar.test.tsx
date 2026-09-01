/**
 * Tests for the metrics bar.
 *
 * Pins the regression that made the dashboard untrustworthy: it reported "Stream: live" and
 * "Face: present — 100% of frames" for a session that had ENDED. Both came from the wrong
 * source. `connected` is the admin page's own SSE transport, which is green whenever the page
 * is open, and face presence was the last value ever received with no staleness check. A
 * closed camera with nobody on the platform therefore rendered identically to an active
 * learner, and the only way to tell was to read the event-log timestamps.
 *
 * Transport and session liveness are now separate stats, and anything derived from a live
 * camera is labelled with WHEN it was observed once the session is no longer active.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { MetricsBar } from "./MetricsBar";
import type { MonitorMetrics } from "@/types/monitor";

function metrics(over: Partial<MonitorMetrics> = {}): MonitorMetrics {
  return {
    total: 200,
    domainCount: 46,
    traceCount: 154,
    eventsPerSec: 0,
    cyclesObserved: 13,
    avgNodeMs: 172,
    faceRatio: 1,
    facePresent: true,
    sessionState: "active",
    lastCycleAt: Date.now(),
    lastCycleAgeMs: 2_000,
    ...over,
  };
}

describe("transport and session are separate", () => {
  it("reports the monitor connection independently of the session", () => {
    render(<MetricsBar metrics={metrics({ sessionState: "ended" })} connected />);
    // The page IS connected; the session is NOT. Both must be visible at once.
    expect(screen.getByText("connected")).toBeInTheDocument();
    expect(screen.getByText("ended")).toBeInTheDocument();
  });

  it("does not claim a session when the transport is down", () => {
    render(<MetricsBar metrics={metrics({ sessionState: "idle" })} connected={false} />);
    expect(screen.getByText("offline")).toBeInTheDocument();
    expect(screen.getByText("none")).toBeInTheDocument();
  });

  it.each([
    ["active", "active"],
    ["stale", "stale"],
    ["ended", "ended"],
    ["idle", "none"],
  ] as const)("renders %s session state as %s", (state, label) => {
    render(<MetricsBar metrics={metrics({ sessionState: state })} connected />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});

describe("face presence is not reported as current once the session is over", () => {
  it("shows present while the session is active", () => {
    render(<MetricsBar metrics={metrics()} connected />);
    expect(screen.getByText("present")).toBeInTheDocument();
    expect(screen.getByText("100% of frames")).toBeInTheDocument();
  });

  it("withholds the verdict and dates the ratio when the session has ended", () => {
    // The exact production case: camera closed, session gone, panel still said present/100%.
    render(
      <MetricsBar
        metrics={metrics({ sessionState: "ended", lastCycleAgeMs: 240_000 })}
        connected
      />,
    );
    expect(screen.queryByText("present")).not.toBeInTheDocument();
    expect(screen.queryByText("100% of frames")).not.toBeInTheDocument();
    expect(screen.getByText(/was 100%, 4m ago/)).toBeInTheDocument();
  });

  it("withholds the verdict when the session has merely gone quiet", () => {
    render(
      <MetricsBar
        metrics={metrics({ sessionState: "stale", lastCycleAgeMs: 90_000 })}
        connected
      />,
    );
    expect(screen.queryByText("present")).not.toBeInTheDocument();
    expect(screen.getByText(/was 100%/)).toBeInTheDocument();
  });

  it("says so plainly when no session has reported at all", () => {
    render(
      <MetricsBar
        metrics={metrics({ sessionState: "idle", faceRatio: null, facePresent: null, lastCycleAgeMs: null })}
        connected
      />,
    );
    expect(screen.getByText("no active session")).toBeInTheDocument();
  });
});

describe("age labels", () => {
  it.each([
    [5_000, /just now/],
    [45_000, /45s ago/],
    [240_000, /4m ago/],
    [7_200_000, /2h ago/],
  ])("formats %ims", (age, pattern) => {
    render(
      <MetricsBar metrics={metrics({ sessionState: "ended", lastCycleAgeMs: age })} connected />,
    );
    // Both the Session hint and the Face hint carry the age, so match on either.
    expect(screen.getAllByText(pattern).length).toBeGreaterThan(0);
  });

  it("does not invent an age it does not have", () => {
    render(
      <MetricsBar
        metrics={metrics({ sessionState: "ended", lastCycleAgeMs: null })}
        connected
      />,
    );
    expect(screen.getByText(/last cycle unknown/)).toBeInTheDocument();
  });
});
