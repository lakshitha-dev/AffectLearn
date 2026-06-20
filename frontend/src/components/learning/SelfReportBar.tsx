"use client";

import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";
import { useReducedMotion } from "@/hooks/use-reduced-motion";
import type { SelfReportAffect } from "@/types/ws-messages";

/**
 * SelfReportBar — the Story 6.2 inline self-report affect widget (ground-truth labeling).
 *
 * The pilot's PRIMARY source of GROUND-TRUTH affect labels. The facial CNN-LSTM and
 * behavioral Bi-LSTM produce *inferred* affect; to validate (and in Phase A train) those
 * models the research team needs the learner's own periodic report. The UX spec is emphatic
 * that this must "feel like a brief reflection, not clinical data collection" and take
 * UNDER 5 SECONDS with a single click and no text input (the "Critical Rule").
 *
 * It is an INLINE bar (never a modal / popup / toast — UX spec "Never Block Learning") shown
 * at a natural pause point. It reads "Quick check: How are you feeling about this material?"
 * with 5 toggle options (Engaged / Confused / Bored / Frustrated / Neutral) plus a "Skip"
 * link. Selecting one highlights it, dims the others, auto-collapses after 1s, and shows a
 * subtle "Thanks" that fades after 2s. Skip collapses with no guilt copy and logs a
 * DELIBERATE skip ({skipped:true, affect:null}) — distinct from missing data (a prompt the
 * learner never reached emits NOTHING).
 *
 * Neutral is a SELF-REPORT-ONLY ground-truth label, NOT a model `AFFECT_STATES` category.
 * The affect model operates over exactly 4 categories (bored/confused/engaged/frustrated);
 * the widget offers those 4 PLUS Neutral — a deliberate 5-value SUPERSET. A learner who feels
 * none of the 4 has a real, researchable state; forcing them into one would pollute the label
 * set. The 5↔4 reconciliation is a downstream research-analysis concern (Epic 6.5 / 8.6), not
 * this widget's job — it faithfully captures + reports all 5.
 *
 * Reuse (do NOT reinvent): the `AdaptiveHintCallout` / `SkipAheadCard` inline shell idiom
 * (token surface/border, rounded, focusable, CSS-driven fade so the global
 * `prefers-reduced-motion` rule clamps it for free), the scoped-Escape idiom (so the lesson
 * page's window Escape→focus-mode handler does NOT fire), and `useReducedMotion()` for the
 * JS-timed sequencing only (the 1s-collapse / 2s-thanks-fade timing semantics still hold).
 *
 * A11y (AC6): the 5 options live in a `role="radiogroup"` `aria-label="How are you feeling?"`
 * container; each is a `role="radio"` with `aria-checked`; roving-tabindex (the group is one
 * tab stop, arrows move focus + selection, Enter/Space selects); the Skip control is an
 * independently keyboard-reachable `<button>`. There is NO countdown / response deadline —
 * the <5s is the time it takes once acting, not a timer pressuring the learner (AC5).
 */

const COLLAPSE_MS = 1000; // selection → bar collapses (AC2)
const THANKS_FADE_MS = 2000; // "Thanks" visible → fade-out begins (AC2: "fades after 2s")
const THANKS_FADE_OUT_MS = 300; // CSS fade-out duration before element is removed

const QUESTION_COPY = "Quick check: How are you feeling about this material?";

// The 5-value self-report vocabulary: the 4 model `AFFECT_STATES`
// (bored/confused/engaged/frustrated) PLUS `neutral`. Neutral is a deliberate
// ground-truth-only label, NOT a model category (see component docstring / Dev Notes).
const OPTIONS: { value: SelfReportAffect; label: string }[] = [
  { value: "engaged", label: "Engaged" },
  { value: "confused", label: "Confused" },
  { value: "bored", label: "Bored" },
  { value: "frustrated", label: "Frustrated" },
  { value: "neutral", label: "Neutral" },
];

export interface SelfReport {
  affect: SelfReportAffect | null;
  skipped: boolean;
}

interface SelfReportBarProps {
  /** Fired once per interaction with the learner's selection or a deliberate skip.
   *  The consumer (lesson page) is responsible for including `prompt_index` and
   *  `section_id` in the upstream WS payload — those are page-scoped concerns, not
   *  component-scoped (the page holds `send` and the hook-derived `promptIndex`). */
  onReport: (report: SelfReport) => void;
}

export function SelfReportBar({ onReport }: SelfReportBarProps) {
  const reducedMotion = useReducedMotion();

  const [selected, setSelected] = useState<SelfReportAffect | null>(null);
  // The active (focused) radio index for the roving-tabindex pattern.
  const [activeIndex, setActiveIndex] = useState(0);
  // Phase flags: collapsed = bar gone (options removed); thanks shown until the 2s fade.
  const [collapsed, setCollapsed] = useState(false);
  // thanksLeaving = true starts the CSS fade-out; thanksGone = true removes the element.
  const [thanksLeaving, setThanksLeaving] = useState(false);
  const [thanksGone, setThanksGone] = useState(false);
  const [visible, setVisible] = useState(false);

  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  // Guard so a rapid second select/skip only fires onReport once.
  const actedRef = useRef(false);

  // Enter animation: start invisible, flip to visible after a rAF so the CSS transition runs.
  useEffect(() => {
    const raf = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  // Clear ALL timers on unmount (no leaked timers / state-update-after-unmount — AC2).
  useEffect(() => {
    return () => {
      for (const t of timersRef.current) clearTimeout(t);
      timersRef.current = [];
    };
  }, []);

  const select = (value: SelfReportAffect) => {
    if (actedRef.current) return;
    actedRef.current = true;
    setSelected(value);
    onReport({ affect: value, skipped: false });
    // Phase 1: collapse the bar after 1s (the highlight/dim is visible until then).
    timersRef.current.push(
      setTimeout(() => {
        setCollapsed(true);
        // Phase 2: after a FURTHER 2s begin the "Thanks" CSS fade-out (opacity → 0).
        timersRef.current.push(
          setTimeout(() => {
            setThanksLeaving(true);
            // Phase 3: after the fade-out duration, fully remove the element.
            timersRef.current.push(
              setTimeout(() => setThanksGone(true), THANKS_FADE_OUT_MS),
            );
          }, THANKS_FADE_MS),
        );
      }, COLLAPSE_MS),
    );
  };

  const skip = () => {
    if (actedRef.current) return;
    actedRef.current = true;
    // Deliberate skip — distinct from missing data. No guilt copy, instant collapse.
    onReport({ affect: null, skipped: true });
    setCollapsed(true);
    setThanksGone(true);
  };

  const moveActive = (delta: number) => {
    setActiveIndex((prev) => {
      const next = (prev + delta + OPTIONS.length) % OPTIONS.length;
      optionRefs.current[next]?.focus();
      return next;
    });
  };

  const handleGroupKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (collapsed) return;
    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
        event.preventDefault();
        moveActive(1);
        break;
      case "ArrowLeft":
      case "ArrowUp":
        event.preventDefault();
        moveActive(-1);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        select(OPTIONS[activeIndex].value);
        break;
      default:
        break;
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      // Mirror AdaptiveHintCallout:124-133 — stopPropagation halts React bubbling and
      // stopImmediatePropagation halts the native event before it reaches window-level
      // listeners (the lesson page's focus-mode Escape handler), so only this bar closes.
      event.stopPropagation();
      event.nativeEvent.stopImmediatePropagation();
      skip();
    }
  };

  // Fully gone once collapsed AND the thanks has faded (or was skipped). Under reduced
  // motion the timing phases still hold (functional, not decorative) — only easing changes.
  if (collapsed && thanksGone) return null;

  // Collapsed but thanks still showing: subtle "Thanks" text that fades out (AC2).
  if (collapsed) {
    return (
      <div
        role="status"
        aria-live="polite"
        className={cn(
          "my-6 text-sm italic text-muted-foreground",
          "transition-opacity ease-out",
          reducedMotion ? "duration-0" : "duration-300",
          thanksLeaving ? "opacity-0" : "opacity-100",
        )}
      >
        Thanks
      </div>
    );
  }

  return (
    <div
      role="group"
      aria-label="Self-report check-in"
      tabIndex={-1}
      onKeyDown={handleKeyDown}
      className={cn(
        "my-6 rounded-lg border border-border bg-surface px-5 py-4",
        "transition-opacity duration-300 ease-out",
        visible ? "opacity-100" : "opacity-0",
      )}
    >
      <p className="text-sm font-medium text-foreground">{QUESTION_COPY}</p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <div
          role="radiogroup"
          aria-label="How are you feeling?"
          onKeyDown={handleGroupKeyDown}
          className="flex flex-wrap gap-2"
        >
          {OPTIONS.map((option, idx) => {
            const isSelected = selected === option.value;
            const dimmed = selected !== null && !isSelected;
            return (
              <button
                key={option.value}
                ref={(el) => {
                  optionRefs.current[idx] = el;
                }}
                type="button"
                role="radio"
                aria-checked={isSelected}
                tabIndex={idx === activeIndex ? 0 : -1}
                disabled={selected !== null}
                onClick={() => select(option.value)}
                className={cn(
                  "rounded-lg border px-3 py-1.5 text-sm font-medium",
                  "transition-[background-color,color,opacity,border-color] duration-200 ease-out",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                  isSelected
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-surface text-foreground hover:bg-primary-soft",
                  dimmed && "opacity-50 text-muted-foreground",
                )}
              >
                {option.label}
              </button>
            );
          })}
        </div>

        {selected === null && (
          <button
            type="button"
            onClick={skip}
            className="ml-1 text-sm text-muted-foreground underline-offset-2 hover:text-primary hover:underline"
          >
            Skip
          </button>
        )}
      </div>
    </div>
  );
}
