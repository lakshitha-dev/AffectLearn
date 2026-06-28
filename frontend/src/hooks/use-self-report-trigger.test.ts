import { describe, it, expect } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useSelfReportTrigger, SECTIONS_PER_PROMPT } from "./use-self-report-trigger";

const T = SECTIONS_PER_PROMPT;

describe("useSelfReportTrigger (AC7 pause-point trigger)", () => {
  it("does not show the widget before SECTIONS_PER_PROMPT completions", () => {
    const { result, rerender } = renderHook((count: number) => useSelfReportTrigger(count), {
      initialProps: 0,
    });
    expect(result.current.showSelfReport).toBe(false);
    rerender(T - 1);
    expect(result.current.showSelfReport).toBe(false);
  });

  it("shows the widget once the completion count reaches the threshold", () => {
    const { result, rerender } = renderHook((count: number) => useSelfReportTrigger(count), {
      initialProps: 0,
    });
    rerender(T);
    expect(result.current.showSelfReport).toBe(true);
    expect(result.current.promptIndex).toBe(0);
  });

  it("resets after a report/skip and does not re-prompt until a further threshold", () => {
    const { result, rerender } = renderHook((count: number) => useSelfReportTrigger(count), {
      initialProps: 0,
    });
    rerender(T);
    expect(result.current.showSelfReport).toBe(true);

    // Learner reports/skips → dismiss records the boundary at the current count.
    act(() => result.current.dismiss());
    rerender(T);
    expect(result.current.showSelfReport).toBe(false);
    expect(result.current.promptIndex).toBe(1);

    // Still below the next boundary (T + T) ...
    rerender(2 * T - 1);
    expect(result.current.showSelfReport).toBe(false);
    // ... a further `threshold` completions triggers the next prompt.
    rerender(2 * T);
    expect(result.current.showSelfReport).toBe(true);
  });

  it("re-bases when the completed count drops (learner moves to a new lesson)", () => {
    const { result, rerender } = renderHook((count: number) => useSelfReportTrigger(count), {
      initialProps: 0,
    });
    rerender(T); // prompt fires in lesson A
    expect(result.current.showSelfReport).toBe(true);
    act(() => result.current.dismiss()); // boundary recorded at T

    rerender(0); // new lesson: per-lesson count resets → boundary re-bases to 0
    expect(result.current.showSelfReport).toBe(false);

    rerender(T); // completing `threshold` sections in lesson B prompts again
    expect(result.current.showSelfReport).toBe(true);
  });

  it("never shows with no pause signal (single-section lesson stays below threshold)", () => {
    const { result, rerender } = renderHook((count: number) => useSelfReportTrigger(count), {
      initialProps: 0,
    });
    rerender(1); // only one section ever completed
    expect(result.current.showSelfReport).toBe(T > 1 ? false : true);
  });

  it("honors a custom threshold", () => {
    const { result, rerender } = renderHook(
      (count: number) => useSelfReportTrigger(count, 3),
      { initialProps: 0 },
    );
    rerender(2);
    expect(result.current.showSelfReport).toBe(false);
    rerender(3);
    expect(result.current.showSelfReport).toBe(true);
  });
});
