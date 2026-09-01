/**
 * Tests for the behaviour panel.
 *
 * Pins the presentation of a suppressed cycle. The backend stopped classifying an all-zeros
 * window — an empty window is not evidence that a learner is engaged, because the negative
 * class in DUX absorbs unannotated time, so classifying it reported "engaged, 99%" whether or
 * not anyone was at the machine. The panel then rendered that absence literally, as
 * `model → — 0%` above an empty softmax, which reads as a broken panel rather than as a
 * deliberate non-observation.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { BehaviorPanel } from "./BehaviorPanel";

const ACTIVE = {
  event_counts: {
    mouse_sample_count: 12,
    mouse_click_count: 2,
    keystroke_count: 8,
    scroll_event_count: 17,
  },
  probs: [0.97, 0.03],
  label: "engaged",
  affect_confidence: 0.97,
  model_kind: "aggregate_confusion_gbdt",
  p_confused: 0.03,
  idle: false,
};

const IDLE = {
  event_counts: {
    mouse_sample_count: 0,
    mouse_click_count: 0,
    keystroke_count: 0,
    scroll_event_count: 0,
  },
  idle: true,
};

describe("an active cycle reports normally", () => {
  it("shows the label, confidence and gate probability", () => {
    render(<BehaviorPanel data={ACTIVE} />);
    expect(screen.getByText("engaged")).toBeInTheDocument();
    // The softmax bar carries the same percentage, so match on either occurrence.
    expect(screen.getAllByText("97%").length).toBeGreaterThan(0);
    expect(screen.getByText("0.030")).toBeInTheDocument();
  });

  it("reads the model identity from the payload rather than hardcoding it", () => {
    render(<BehaviorPanel data={ACTIVE} />);
    expect(screen.getByText(/aggregate_confusion_gbdt/)).toBeInTheDocument();
  });

  it("renders the softmax distribution", () => {
    render(<BehaviorPanel data={ACTIVE} />);
    expect(screen.getByText(/Classification \(softmax\)/)).toBeInTheDocument();
  });
});

describe("a suppressed idle cycle explains itself", () => {
  it("does not render an absent label as a result", () => {
    render(<BehaviorPanel data={IDLE} />);
    // The old rendering: an em-dash label beside "0%", indistinguishable from a failure.
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    expect(screen.getByText("no interaction this cycle")).toBeInTheDocument();
  });

  it("says why affect was not inferred", () => {
    render(<BehaviorPanel data={IDLE} />);
    expect(screen.getByText(/affect was not inferred/)).toBeInTheDocument();
  });

  it("states that an empty window is not evidence of engagement", () => {
    // The whole point of the suppression, and the thing a supervisor will ask about.
    render(<BehaviorPanel data={IDLE} />);
    expect(screen.getByText(/not evidence that a learner is engaged/)).toBeInTheDocument();
  });

  it("confirms the feature window is still recorded", () => {
    // Suppression must not read as data loss -- Phase A still gets the window.
    render(<BehaviorPanel data={IDLE} />);
    expect(screen.getByText(/feature window is\s+still recorded/)).toBeInTheDocument();
  });

  it("hides the softmax, which is meaningless on a suppressed cycle", () => {
    render(<BehaviorPanel data={IDLE} />);
    expect(screen.queryByText(/Classification \(softmax\)/)).not.toBeInTheDocument();
  });

  it("still shows the zero event counts as the evidence for suppression", () => {
    render(<BehaviorPanel data={IDLE} />);
    expect(screen.getByText("mouse")).toBeInTheDocument();
    expect(screen.getByText("keys")).toBeInTheDocument();
  });
});
