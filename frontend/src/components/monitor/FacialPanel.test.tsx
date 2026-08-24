/**
 * Tests for the facial panel.
 *
 * Three regressions are pinned here, all of which shipped to production:
 *   1. `p_confused` was absent from the payload, so the panel fell back to the superseded
 *      4-level engagement display and showed "level 0 (legacy 4-level payload)".
 *   2. `dropped_reasons` was never forwarded by the backend, so the drop breakdown rendered a
 *      permanent "no face: 0 · low confidence: 0" — a fake zero, not a measurement.
 *   3. There was no way to see that the channel's probabilities never reached the gate, which is
 *      what made a whole session of flat 0.48–0.55 readings look like normal operation.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { createElement } from "react";

vi.mock("recharts", () => ({}));

import { FacialPanel } from "./FacialPanel";

const CYCLE = {
  frames_captured: 30,
  dropped_frames: 0,
  probs: [0.45, 0.55],
  p_confused: 0.55,
  label: "confused",
  model_kind: "binary_confusion",
};

describe("FacialPanel — confusion output", () => {
  it("shows P(confused) rather than the legacy engagement level", () => {
    render(createElement(FacialPanel, { data: CYCLE, modelAvailable: true }));
    expect(screen.getByText("0.550")).toBeInTheDocument();
    expect(screen.queryByText(/legacy 4-level payload/i)).not.toBeInTheDocument();
  });

  it("still renders the legacy display for an old buffered event", () => {
    render(
      createElement(FacialPanel, {
        data: { frames_captured: 30, dropped_frames: 0, engagement_level: 1 },
        modelAvailable: true,
      }),
    );
    expect(screen.getByText(/legacy 4-level payload/i)).toBeInTheDocument();
  });

  it("reports an inference error instead of a distribution", () => {
    render(
      createElement(FacialPanel, {
        data: { frames_captured: 0, dropped_frames: 0, error: "model_unavailable" },
        modelAvailable: false,
      }),
    );
    // The amber "model not loaded" banner also mentions model_unavailable, so scope to the
    // inference line.
    expect(screen.getByText(/^inference:/)).toBeInTheDocument();
  });
});

describe("FacialPanel — drop breakdown", () => {
  it("distinguishes 'not reported' from a measured zero", () => {
    // No dropped_reasons key at all: the panel must NOT claim zero drops.
    render(createElement(FacialPanel, { data: CYCLE, modelAvailable: true }));
    expect(screen.getByText(/not reported this cycle/i)).toBeInTheDocument();
    expect(screen.queryByText(/no face: 0/)).not.toBeInTheDocument();
  });

  it("renders real counts when the backend forwards them", () => {
    render(
      createElement(FacialPanel, {
        data: { ...CYCLE, dropped_reasons: { no_face: 4, low_confidence: 2 } },
        modelAvailable: true,
      }),
    );
    expect(screen.getByText(/no face: 4/)).toBeInTheDocument();
    expect(screen.getByText(/low confidence: 2/)).toBeInTheDocument();
  });
});

describe("FacialPanel — calibration verdict", () => {
  const stuck = { n: 40, min: 0.48, max: 0.55, mean: 0.51, overThreshold: 0, reachedThreshold: false };
  const healthy = { n: 40, min: 0.02, max: 0.88, mean: 0.3, overThreshold: 6, reachedThreshold: true };

  it("warns when the channel never reached the gate in the window", () => {
    render(
      createElement(FacialPanel, {
        data: CYCLE,
        modelAvailable: true,
        stats: stuck,
        threshold: 0.7,
      }),
    );
    expect(screen.getByText(/never reached the gate/i)).toBeInTheDocument();
    expect(screen.getByText(/fusion input only/i)).toBeInTheDocument();
    // The observed range is shown, so the claim is checkable.
    expect(screen.getByText(/0\.480/)).toBeInTheDocument();
  });

  it("reports the crossing count once the channel does reach the gate", () => {
    render(
      createElement(FacialPanel, {
        data: CYCLE,
        modelAvailable: true,
        stats: healthy,
        threshold: 0.7,
      }),
    );
    expect(screen.getByText(/Crossed the gate on 6 of 40/i)).toBeInTheDocument();
    expect(screen.queryByText(/never reached the gate/i)).not.toBeInTheDocument();
  });

  it("renders nothing when there is no windowed data yet", () => {
    render(
      createElement(FacialPanel, {
        data: CYCLE,
        modelAvailable: true,
        stats: { n: 0 },
        threshold: 0.7,
      }),
    );
    expect(screen.queryByText(/observed P\(confused\)/i)).not.toBeInTheDocument();
  });

  it("does not claim 'never reached' without a threshold to compare against", () => {
    render(
      createElement(FacialPanel, { data: CYCLE, modelAvailable: true, stats: stuck }),
    );
    expect(screen.queryByText(/never reached the gate/i)).not.toBeInTheDocument();
  });
});
