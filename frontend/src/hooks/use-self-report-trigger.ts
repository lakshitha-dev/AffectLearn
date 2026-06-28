"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * useSelfReportTrigger — the Story 6.2 pause-point trigger for the self-report widget.
 *
 * The lesson page renders all sections at once and navigates by scrolling; there is NO
 * existing "sections viewed" counter and no per-section route. The "every 2-3 sections /
 * ~10-15 min" pause point is therefore DERIVED from the cleanest signal the page already
 * has: SECTION COMPLETION (`completedSectionIds` / `handleMarkComplete`). We count distinct
 * completions since the last prompt; once the delta reaches `SECTIONS_PER_PROMPT` (= 3) the
 * widget shows, then the boundary resets after a report/skip. This maps "every 2-3 sections"
 * to a concrete, testable rule and reuses existing state — a scroll-spy / IntersectionObserver
 * is deliberately avoided (over-engineering for a pilot instrument; Dev Notes "Pause-point
 * trigger", Open Question #1).
 *
 * Contract:
 *  - Pass the CURRENT set of completed section ids on every render. The hook diffs it against
 *    the count at the last prompt boundary; when `distinctCompleted - boundary >= threshold`
 *    it sets `showSelfReport = true`.
 *  - The widget shows AT MOST ONE prompt at a time and does NOT re-prompt immediately after a
 *    response/skip — `dismiss()` records the new boundary at the current completed count and
 *    increments `promptIndex` so downstream analysis can order prompts within the session.
 *  - With no pause signal (e.g. a single-section lesson that never reaches the threshold) the
 *    widget simply never shows (graceful absence, no error) — AC7.
 */

// Pause-point cadence: a prompt fires every N section completions ("every 2-3 sections").
// Set to 2 so it triggers within short lessons (the pilot lessons have ~2 sections each).
export const SECTIONS_PER_PROMPT = 2;

interface UseSelfReportTriggerResult {
  /** True when a pause point has been reached and the widget should render. */
  showSelfReport: boolean;
  /** Session-scoped prompt ordinal (0-based) for the prompt currently/last shown. */
  promptIndex: number;
  /** Call after a report/skip: hide the widget, reset the boundary, advance promptIndex. */
  dismiss: () => void;
}

export function useSelfReportTrigger(
  completedCount: number,
  threshold: number = SECTIONS_PER_PROMPT,
): UseSelfReportTriggerResult {
  // The completed-count at the last prompt boundary (start at 0 — first prompt fires once
  // `threshold` distinct completions have accrued). Held in STATE (not a ref) so advancing
  // the boundary on dismiss re-renders and re-evaluates `showSelfReport`.
  const [boundary, setBoundary] = useState(0);
  const [promptIndex, setPromptIndex] = useState(0);

  // Re-base when the completed count drops below the boundary. The lesson page feeds a
  // PER-LESSON completed count, so navigating to a new lesson resets it toward 0; without
  // this, a boundary carried over from the previous lesson would suppress every prompt in
  // all later lessons. Re-basing makes each lesson start fresh.
  useEffect(() => {
    if (completedCount < boundary) setBoundary(completedCount);
  }, [completedCount, boundary]);

  const showSelfReport = completedCount - boundary >= threshold;

  const dismiss = useCallback(() => {
    // Record the new boundary at the current completed count so the next prompt requires a
    // FURTHER `threshold` completions — no immediate re-prompt.
    setBoundary(completedCount);
    setPromptIndex((i) => i + 1);
  }, [completedCount]);

  return { showSelfReport, promptIndex, dismiss };
}
