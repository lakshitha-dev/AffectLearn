/**
 * What "Skip ahead" should do, as a decision table.
 *
 * The bug this pins: on the LAST section the handler advanced `currentIndex` to itself and
 * stopped — a documented "graceful no-op". The learner accepted the suggestion, the card
 * disappeared, and nothing moved. The Next button on that same section crosses into the following
 * lesson. A control the SYSTEM offered unprompted is the worst place to put one that silently
 * does nothing.
 *
 * The logic lives in the lesson page, which mounts MediaPipe, a WebSocket and the whole agent
 * client, so the decision is extracted here as a pure function and tested directly rather than by
 * standing all of that up.
 */

import { describe, it, expect } from "vitest";

/** Mirrors the branch in `handleSkipAhead`. */
export function skipAheadTarget(
  currentIndex: number,
  sectionCount: number
): { action: "next-section"; index: number } | { action: "leave-lesson" } {
  const idx = Math.min(currentIndex, sectionCount - 1);
  if (idx >= sectionCount - 1) return { action: "leave-lesson" };
  return { action: "next-section", index: idx + 1 };
}

describe("skipAheadTarget", () => {
  it("advances to the next section mid-lesson", () => {
    expect(skipAheadTarget(0, 4)).toEqual({ action: "next-section", index: 1 });
    expect(skipAheadTarget(2, 4)).toEqual({ action: "next-section", index: 3 });
  });

  it("leaves the lesson on the last section instead of doing nothing", () => {
    // The reported bug: clicking Skip ahead here used to move nothing at all.
    expect(skipAheadTarget(3, 4)).toEqual({ action: "leave-lesson" });
  });

  it("leaves the lesson when the lesson has a single section", () => {
    expect(skipAheadTarget(0, 1)).toEqual({ action: "leave-lesson" });
  });

  it("never returns an index past the end", () => {
    for (let count = 1; count <= 6; count += 1) {
      for (let i = 0; i < count; i += 1) {
        const target = skipAheadTarget(i, count);
        if (target.action === "next-section") {
          expect(target.index).toBeLessThan(count);
          expect(target.index).toBe(i + 1);
        }
      }
    }
  });

  it("tolerates an index past the end rather than skipping into nothing", () => {
    // `currentIndex` is clamped elsewhere too, but a stale value must not produce index 9.
    expect(skipAheadTarget(9, 3)).toEqual({ action: "leave-lesson" });
  });
});
