/**
 * Tests for the live struggle-counter send.
 *
 * These counters were only ever sent at COMPLETION, in the section-progress request body. That
 * is the right place for the training record and useless for intervening: by the time a learner
 * finishes a section the moment has passed, and a learner who gets stuck and gives up never
 * completes it at all — so the counters describing the hardest case were the ones never sent.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";

import { usePerformanceWindow } from "./use-performance-window";

const CYCLE_MS = 30_000;

const SNAPSHOT = {
  backNavCount: 2,
  showAnswerUsed: true,
  quizAttemptCount: 4,
  quizIncorrectCount: 3,
  timeOnSectionS: 240,
};

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

function mount(over: Partial<Parameters<typeof usePerformanceWindow>[0]> = {}) {
  const send = vi.fn();
  const snapshot = vi.fn(() => SNAPSHOT);
  const props = { send, sectionId: "sec-1", snapshot, ...over };
  const view = renderHook((p: typeof props) => usePerformanceWindow(p), {
    initialProps: props,
  });
  return { send, snapshot, view, props };
}

describe("usePerformanceWindow", () => {
  it("sends nothing before the first cycle elapses", () => {
    const { send } = mount();
    vi.advanceTimersByTime(CYCLE_MS - 1);
    expect(send).not.toHaveBeenCalled();
  });

  it("sends the counters once per cycle", () => {
    const { send } = mount();
    vi.advanceTimersByTime(CYCLE_MS * 3);
    expect(send).toHaveBeenCalledTimes(3);
  });

  it("sends snake_case on the wire", () => {
    // The WebSocket protocol is snake_case in both directions — a deliberate exception to the
    // REST camelCase rule. Sending camelCase here would be silently dropped by the handler's
    // whitelist rather than failing loudly.
    const { send } = mount();
    vi.advanceTimersByTime(CYCLE_MS);

    const envelope = send.mock.calls[0][0];
    expect(envelope.type).toBe("performance_window");
    expect(envelope.data).toMatchObject({
      back_nav_count: 2,
      show_answer_used: true,
      quiz_attempt_count: 4,
      quiz_incorrect_count: 3,
      time_on_section_s: 240,
      section_id: "sec-1",
    });
  });

  it("sends only counts, never content", () => {
    // Nothing here that is not already recorded at completion: no answers, no text, no learner
    // identifier beyond the section.
    const { send } = mount();
    vi.advanceTimersByTime(CYCLE_MS);

    const keys = Object.keys(send.mock.calls[0][0].data);
    expect(keys.every((k) => /^(cycle_number|section_id|[a-z_]+_(count|used|s))$/.test(k))).toBe(
      true,
    );
  });

  it("numbers the cycles", () => {
    const { send } = mount();
    vi.advanceTimersByTime(CYCLE_MS * 2);

    expect(send.mock.calls[0][0].data.cycle_number).toBe(1);
    expect(send.mock.calls[1][0].data.cycle_number).toBe(2);
  });

  it("sends nothing when the learner is not on a section", () => {
    const { send } = mount({ sectionId: undefined });
    vi.advanceTimersByTime(CYCLE_MS * 2);
    expect(send).not.toHaveBeenCalled();
  });

  it("sends nothing when there are no counters for the section", () => {
    // A section the learner has not entered has no observation, and inventing zeros for it would
    // report a calm learner where there is simply no data.
    const { send } = mount({ snapshot: vi.fn(() => undefined) });
    vi.advanceTimersByTime(CYCLE_MS * 2);
    expect(send).not.toHaveBeenCalled();
  });

  it("can be disabled", () => {
    const { send } = mount({ enabled: false });
    vi.advanceTimersByTime(CYCLE_MS * 2);
    expect(send).not.toHaveBeenCalled();
  });

  it("keeps one timer across section changes", () => {
    // Depending on `sectionId` directly would tear down and recreate the interval on every
    // section change, restarting the 30s clock — so a learner moving between sections quickly
    // would never complete a cycle and the channel would never fire.
    const { send, view, props } = mount();

    vi.advanceTimersByTime(CYCLE_MS - 5_000);
    view.rerender({ ...props, sectionId: "sec-2" });
    vi.advanceTimersByTime(5_000);

    expect(send).toHaveBeenCalledTimes(1);
    expect(send.mock.calls[0][0].data.section_id).toBe("sec-2");
  });

  it("stops on unmount", () => {
    const { send, view } = mount();
    view.unmount();
    vi.advanceTimersByTime(CYCLE_MS * 3);
    expect(send).not.toHaveBeenCalled();
  });
});
