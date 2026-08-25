/**
 * Tests for the per-cycle face-presence strip.
 *
 * This is the diagnostic that answers "was the learner even in front of the camera" when an affect
 * trace looks wrong. Before it existed there was no way to tell an empty chair from a calm reader:
 * faceless frames are kept as centre crops for training parity, so `frames_captured` reads 30
 * either way.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { createElement } from "react";
import type { FacePresencePoint } from "@/types/monitor";

import { FacePresenceStrip } from "./FacePresenceStrip";

function pt(over: Partial<FacePresencePoint> = {}): FacePresencePoint {
  return {
    t: 1_700_000_000_000,
    cycle: 1,
    seen: 28,
    captured: 30,
    ratio: 0.933,
    absent: false,
    ...over,
  };
}

describe("FacePresenceStrip", () => {
  it("shows an empty state rather than an empty box", () => {
    render(createElement(FacePresenceStrip, { series: [] }));
    expect(screen.getByText(/no face-presence data yet/i)).toBeInTheDocument();
  });

  it("renders one cell per cycle", () => {
    const series = [pt({ cycle: 1 }), pt({ cycle: 2 }), pt({ cycle: 3 })];
    render(createElement(FacePresenceStrip, { series }));
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  it("summarises how many cycles had a face", () => {
    const series = [pt({ cycle: 1 }), pt({ cycle: 2, absent: true, seen: 2, ratio: 0.067 })];
    render(createElement(FacePresenceStrip, { series }));
    expect(screen.getByText(/1\/2/)).toBeInTheDocument();
    expect(screen.getByText(/\(50%\)/)).toBeInTheDocument();
  });

  it("labels each cell with its cycle and frame ratio for hover inspection", () => {
    render(createElement(FacePresenceStrip, { series: [pt({ cycle: 7 })] }));
    expect(screen.getByRole("listitem")).toHaveAttribute(
      "title",
      expect.stringContaining("cycle 7") as unknown as string,
    );
    expect(screen.getByRole("listitem").getAttribute("title")).toContain("28/30");
  });

  it("marks an absent cycle and says affect was suppressed", () => {
    const series = [pt({ cycle: 1, absent: true, seen: 0, ratio: 0 })];
    render(createElement(FacePresenceStrip, { series }));
    expect(screen.getByRole("listitem").getAttribute("title")).toContain("absent");
    expect(screen.getByText(/facial affect was suppressed/i)).toBeInTheDocument();
  });

  it("says nothing about suppression when every cycle had a face", () => {
    render(createElement(FacePresenceStrip, { series: [pt(), pt({ cycle: 2 })] }));
    expect(screen.queryByText(/suppressed/i)).not.toBeInTheDocument();
  });

  it("caps at the most recent N cycles", () => {
    const series = Array.from({ length: 60 }, (_, i) => pt({ cycle: i + 1 }));
    render(createElement(FacePresenceStrip, { series, max: 10 }));
    expect(screen.getAllByRole("listitem")).toHaveLength(10);
    // The newest cycles, not the oldest.
    expect(screen.getAllByRole("listitem")[9].getAttribute("title")).toContain("cycle 60");
  });

  it("pluralises a single cycle correctly", () => {
    render(createElement(FacePresenceStrip, { series: [pt()] }));
    expect(screen.getByText(/last 1 cycle$/i)).toBeInTheDocument();
  });
});
