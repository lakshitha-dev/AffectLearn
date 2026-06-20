import { describe, it, expect } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useSelfReportTrigger, SECTIONS_PER_PROMPT } from "./use-self-report-trigger";

describe("useSelfReportTrigger (AC7 pause-point trigger)", () => {
  it("does not show the widget before SECTIONS_PER_PROMPT completions", () => {
    const { result, rerender } = renderHook((count: number) => useSelfReportTrigger(count), {
      initialProps: 0,
    });
    expect(result.current.showSelfReport).toBe(false);
    rerender(1);
    expect(result.current.showSelfReport).toBe(false);
    rerender(2);
    expect(result.current.showSelfReport).toBe(false);
  });

  it("shows the widget once the completion count reaches the threshold (3)", () => {
    const { result, rerender } = renderHook((count: number) => useSelfReportTrigger(count), {
      initialProps: 0,
    });
    rerender(SECTIONS_PER_PROMPT);
    expect(result.current.showSelfReport).toBe(true);
    expect(result.current.promptIndex).toBe(0);
  });

  it("resets after a report/skip and does not re-prompt until a further threshold", () => {
    const { result, rerender } = renderHook((count: number) => useSelfReportTrigger(count), {
      initialProps: 0,
    });
    rerender(3);
    expect(result.current.showSelfReport).toBe(true);

    // Learner reports/skips → dismiss records the boundary at the current count (3).
    act(() => result.current.dismiss());
    rerender(3);
    expect(result.current.showSelfReport).toBe(false);
    expect(result.current.promptIndex).toBe(1);

    // 4, 5 still below the next boundary (3 + 3 = 6).
    rerender(5);
    expect(result.current.showSelfReport).toBe(false);
    // A further 3 completions (total 6) triggers the next prompt.
    rerender(6);
    expect(result.current.showSelfReport).toBe(true);
  });

  it("never shows with no pause signal (single-section lesson stays below threshold)", () => {
    const { result, rerender } = renderHook((count: number) => useSelfReportTrigger(count), {
      initialProps: 0,
    });
    rerender(1); // only one section ever completed
    expect(result.current.showSelfReport).toBe(false);
  });

  it("honors a custom threshold", () => {
    const { result, rerender } = renderHook(
      (count: number) => useSelfReportTrigger(count, 2),
      { initialProps: 0 },
    );
    rerender(1);
    expect(result.current.showSelfReport).toBe(false);
    rerender(2);
    expect(result.current.showSelfReport).toBe(true);
  });
});
