"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * useSelfReportTrigger — the Story 6.2 pause-point trigger for the self-report widget.
 *
 * The lesson page renders all sections at once and navigates by scrolling; there is NO
 * existing "sections viewed" counter and no per-section route. The "every 2-3 sections /
 * ~10-15 min" pause point is therefore DERIVED from the cleanest signal the page already
 * has: SECTION COMPLETION (`completedSectionIds` / `handleMarkComplete`). We count distinct
 * completions since the last prompt; once the delta reaches `SECTIONS_PER_PROMPT` (= 2) the
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
 *
 * Prompt-reactivity control (pre-pilot, research action item #7): a fraction of due prompts
 * are RANDOMLY OMITTED (`options.omissionRate`, default 0 = off). An omitted prompt is never
 * shown; the hook silently advances the boundary as if dismissed and fires `options.onOmit`
 * so the consumer can log a `self_report {omitted:true}` marker. Comparing behavioral windows
 * after a SHOWN prompt vs an OMITTED (would-be) prompt estimates the prompt's own reactive
 * effect (Hawthorne / measurement reactivity). The show-vs-omit coin is flipped ONCE per
 * boundary (memoised in a ref) so re-renders never re-roll and the widget never flashes.
 */

// Pause-point cadence: a prompt fires every N section completions ("every 2-3 sections").
// Pilot value is 2, so it triggers within short lessons (the pilot lessons have ~2 sections).
//
// BOOTSTRAP OVERRIDE (single-subject collection, Aug 2026): set to 1. Windows are labelled by
// their section's intended affect (AFFECT_SECTION_CODEBOOK.md) and the self-report serves as
// the per-section MANIPULATION CHECK, so one report per section is what the scheme needs.
// REVERT to 2 before the Phase A pilot.
export const SECTIONS_PER_PROMPT = 1;

// Fraction of due self-report prompts to randomly omit in the pilot (research action item #7).
//
// BOOTSTRAP OVERRIDE (single-subject collection, Aug 2026): set to 0. Omission exists to
// estimate prompt reactivity by comparing windows after a shown vs an omitted prompt — a
// BETWEEN-participant control that cannot be estimated at n=1, where it is pure label loss.
// REVERT to 0.2 before the Phase A pilot; the reactivity control is load-bearing there.
export const SELF_REPORT_OMISSION_RATE = 0;

interface UseSelfReportTriggerOptions {
  /** Probability (0-1) that a due prompt is omitted instead of shown. Default 0 (never omit). */
  omissionRate?: number;
  /** RNG in [0,1); injectable for deterministic tests. Default `Math.random`. */
  random?: () => number;
  /** Called once when a due prompt is omitted, with the omitted prompt's index (for logging). */
  onOmit?: (promptIndex: number) => void;
}

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
  options: UseSelfReportTriggerOptions = {},
): UseSelfReportTriggerResult {
  const { omissionRate = 0, random = Math.random, onOmit } = options;

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

  const due = completedCount - boundary >= threshold;

  // Flip the show-vs-omit coin exactly ONCE per boundary, synchronously during render so the
  // widget never flashes before an effect can hide it. Memoised in a ref keyed by boundary;
  // only rolled when omission is enabled (so the default path stays pure and deterministic).
  const decisionRef = useRef<{ boundary: number; omit: boolean } | null>(null);
  let omit = false;
  if (due && omissionRate > 0) {
    if (decisionRef.current?.boundary !== boundary) {
      decisionRef.current = { boundary, omit: random() < omissionRate };
    }
    omit = decisionRef.current.omit;
  }

  // On an omitted prompt, silently advance (as dismiss would) and notify for logging. Fires
  // once: advancing the boundary makes `due` false, so the effect will not re-run for it.
  useEffect(() => {
    if (due && omit) {
      onOmit?.(promptIndex);
      setBoundary(completedCount);
      setPromptIndex((i) => i + 1);
    }
  }, [due, omit, completedCount, onOmit, promptIndex]);

  const showSelfReport = due && !omit;

  const dismiss = useCallback(() => {
    // Record the new boundary at the current completed count so the next prompt requires a
    // FURTHER `threshold` completions — no immediate re-prompt.
    setBoundary(completedCount);
    setPromptIndex((i) => i + 1);
  }, [completedCount]);

  return { showSelfReport, promptIndex, dismiss };
}
