"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { useReducedMotion } from "@/hooks/use-reduced-motion";
import type { Adaptation } from "@/stores/adaptation-store";

/**
 * BreakSuggestionCard — the overlay consumer of the Story 5.3 `adaptationQueue`'s
 * single `suggest_break` action (Story 5.5).
 *
 * It is the "emotional peak" of the adaptive loop: when extended frustration is
 * detected the agent pipeline emits `suggest_break` and this card surfaces a calm,
 * caring recommendation OVER the lesson content. It is a **semi-transparent overlay,
 * NOT a true modal** — per the "Never Block Learning" principle the lesson content
 * stays visible (~30% behind a translucent backdrop) and background scroll is NEVER
 * locked. The learner can dismiss and continue at any time.
 *
 * Three-phase local state machine (no queue mutation):
 *   - `suggestion`    → caring prompt + "Take a break" / "I'm good, continue"
 *   - `timer`         → circular SVG countdown (default 5 min, `breakSeconds` prop),
 *                       "Take your time…" message, optional decorative breathing
 *                       animation, and an early-return control
 *   - `welcome-back`  → "Welcome back! Ready to continue?" + a resume control
 *
 * A11y: `role="alertdialog"` + `aria-label="Break suggestion"` + `aria-modal`, focus
 * is trapped within the card (focus moves to the primary button on open, Tab/Shift+Tab
 * cycle within the card, focus restored on close), and Escape dismisses. The Escape
 * handler is SCOPED to the card — it calls `stopPropagation()` + the native
 * `stopImmediatePropagation()` so it does NOT also fire the lesson page's window-level
 * keydown Escape→focus-mode handler (mirrors `AdaptiveHintCallout.tsx`).
 *
 * Reduced motion: appear (fade-in + scale-up 300ms), dismiss (fade-out) and the
 * breathing animation are CSS/Tailwind driven so the global
 * `@media (prefers-reduced-motion: reduce)` rule in `globals.css` clamps them to
 * ~instant for free; the looping breathing animation is additionally gated behind the
 * existing `useReducedMotion()` hook so it renders static (no scaling) under reduce.
 *
 * Overlay-vs-modal decision (documented variance): a HAND-ROLLED overlay + minimal
 * focus trap is used rather than Radix Dialog. Radix `modal` locks body scroll and
 * `aria-hidden`s siblings (violating "content accessible behind / no scroll-lock"),
 * while Radix `modal={false}` disables its focus trap (so a trap would be hand-rolled
 * regardless). The hand-rolled path keeps full control over the translucent backdrop,
 * scroll behavior and the scoped-Escape native-event handling. (The empty
 * `components/ui/dialog.tsx` placeholder is the user's parallel work — NOT used here.)
 *
 * Adapted-content boundary: this component does NOT generate or fetch the alternative
 * explanation / adapted content. The Content Adapter (5.2) produced it and 5.3
 * delivered it into the queue; on resume 5.5 simply closes and lets the resume flow
 * surface whatever is next (e.g. the inline `show_*` callout 5.4 renders, or the
 * section the learner returns to). No LLM call, no content fetch here.
 *
 * Queue ownership (Open Question #1): the suggestion→timer→welcome-back→dismissed
 * lifecycle is LOCAL UI state. This component never mutates the queue and never
 * `dismissAdaptation`s any item (matching the 5.4 precedent — the queue stays a
 * faithful research log). `onDismiss` is a non-mutating hook point left for future
 * research-logging of "break suggested / taken / declined".
 */

const FADE_OUT_MS = 200;
const DEFAULT_BREAK_SECONDS = 300; // 5 minutes (AC2)
const RING_RADIUS = 52;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

type Phase = "suggestion" | "timer" | "welcome-back";

interface BreakSuggestionCardProps {
  /** The `suggest_break` adaptation this card renders (queue item, not mutated). */
  adaptation: Adaptation;
  /** Called after the fade-out completes when the overlay is fully dismissed. */
  onDismiss: () => void;
  /** Break duration in seconds; defaults to 300 (5 minutes). */
  breakSeconds?: number;
}

function formatTime(totalSeconds: number): string {
  const safe = Math.max(0, totalSeconds);
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function BreakSuggestionCard({
  adaptation,
  onDismiss,
  breakSeconds = DEFAULT_BREAK_SECONDS,
}: BreakSuggestionCardProps) {
  const reducedMotion = useReducedMotion();

  const [phase, setPhase] = useState<Phase>("suggestion");
  const [remaining, setRemaining] = useState(breakSeconds);
  // Drives the enter (fade-in + scale-up) animation: starts false so the overlay
  // mounts at opacity-0/scale-95, then a rAF-deferred effect flips it true.
  const [visible, setVisible] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const cardRef = useRef<HTMLDivElement | null>(null);
  const primaryButtonRef = useRef<HTMLButtonElement | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fadeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Element focused before the card opened, restored on close.
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);

  // adaptation.text is intentionally unused for rendering copy (exact UX strings are
  // used per spec); referenced here only to acknowledge the owned queue item.
  void adaptation;

  // Enter animation (opacity-0 scale-95 → opacity-100 scale-100 via CSS transition).
  useEffect(() => {
    previouslyFocusedRef.current = (document.activeElement as HTMLElement) ?? null;
    const raf = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  // Focus the primary button on open (focus-trap entry point).
  useEffect(() => {
    primaryButtonRef.current?.focus();
  }, [phase]);

  // Countdown: run only during the timer phase; clear on phase change AND unmount so
  // it is deterministic and never fires post-unmount (testable with fake timers).
  useEffect(() => {
    if (phase !== "timer") return;
    intervalRef.current = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          if (intervalRef.current) clearInterval(intervalRef.current);
          intervalRef.current = null;
          setPhase("welcome-back");
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = null;
    };
  }, [phase]);

  // Clear any pending fade-out timer on unmount.
  useEffect(() => {
    return () => {
      if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current);
    };
  }, []);

  const handleDismiss = () => {
    if (leaving || dismissed) return;
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setLeaving(true);
    const finish = () => {
      setLeaving(false);
      setDismissed(true);
      // Restore focus to where it was before the card opened (focus-trap exit).
      previouslyFocusedRef.current?.focus?.();
      onDismiss();
    };
    if (reducedMotion) {
      finish();
      return;
    }
    fadeTimerRef.current = setTimeout(finish, FADE_OUT_MS);
  };

  const handleEarlyReturn = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setPhase("welcome-back");
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      // stopPropagation halts React synthetic bubbling; stopImmediatePropagation halts
      // the underlying native event from reaching window-level listeners (the lesson
      // page's focus-mode Escape handler at page.tsx:75-85), so only the card dismisses.
      event.stopPropagation();
      event.nativeEvent.stopImmediatePropagation();
      handleDismiss();
      return;
    }
    if (event.key === "Tab") {
      // Minimal focus trap: cycle Tab/Shift+Tab within the card.
      const card = cardRef.current;
      if (!card) return;
      const focusable = card.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (event.shiftKey) {
        if (active === first || !card.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last || !card.contains(active)) {
        event.preventDefault();
        first.focus();
      }
    }
  };

  if (dismissed) return null;

  const progressOffset =
    RING_CIRCUMFERENCE * (1 - Math.max(0, Math.min(1, remaining / breakSeconds)));

  return (
    <div
      // Translucent, NON-opaque backdrop so the lesson content reads through at ~30%.
      // No scroll-lock is applied (intentional — overlay, not a true modal).
      className={cn(
        "fixed inset-0 z-50 flex items-center justify-center bg-background/70 p-4",
        "transition-opacity duration-300 ease-out",
        leaving ? "opacity-0 duration-200" : visible ? "opacity-100" : "opacity-0",
      )}
    >
      <div
        ref={cardRef}
        role="alertdialog"
        aria-modal="true"
        aria-label="Break suggestion"
        aria-describedby="break-suggestion-message"
        onKeyDown={handleKeyDown}
        className={cn(
          "w-full max-w-md rounded-xl border border-border bg-surface px-6 py-6 shadow-lg",
          "transition-[opacity,transform] duration-300 ease-out",
          leaving
            ? "opacity-0 scale-95 duration-200"
            : visible
              ? "opacity-100 scale-100"
              : "opacity-0 scale-95",
        )}
      >
        {/* Stable description node for aria-describedby — always in the DOM so
            the alertdialog's description is never a dangling reference across
            phase transitions (suggestion → timer → welcome-back). Screen readers
            announce this on dialog open; the visible per-phase copy below may
            differ but this provides a permanent accessible description. */}
        <span id="break-suggestion-message" className="sr-only">
          You&apos;ve been working hard. A short break can help things click.
        </span>

        {phase === "suggestion" && (
          <div className="text-center">
            <p
              className="text-lg font-medium leading-relaxed text-foreground"
            >
              You&apos;ve been working hard. A short break can help things click.
            </p>
            <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-center">
              <Button ref={primaryButtonRef} onClick={() => setPhase("timer")}>
                Take a break
              </Button>
              <Button variant="outline" onClick={handleDismiss}>
                I&apos;m good, continue
              </Button>
            </div>
          </div>
        )}

        {phase === "timer" && (
          <div className="flex flex-col items-center text-center">
            <div className="relative flex h-36 w-36 items-center justify-center">
              {/* Decorative guided-breathing pulse layered behind the ring. It is
                  CSS-driven (animate-pulse) so the global reduced-motion rule clamps
                  it, AND additionally rendered static when useReducedMotion() is true. */}
              <span
                aria-hidden="true"
                className={cn(
                  "absolute h-28 w-28 rounded-full bg-primary/10",
                  reducedMotion ? "" : "animate-pulse",
                )}
              />
              <svg
                className="absolute h-36 w-36 -rotate-90"
                viewBox="0 0 120 120"
                aria-hidden="true"
              >
                <circle
                  cx="60"
                  cy="60"
                  r={RING_RADIUS}
                  fill="none"
                  stroke="rgb(var(--border))"
                  strokeWidth="8"
                />
                <circle
                  cx="60"
                  cy="60"
                  r={RING_RADIUS}
                  fill="none"
                  stroke="rgb(var(--primary))"
                  strokeWidth="8"
                  strokeLinecap="round"
                  strokeDasharray={RING_CIRCUMFERENCE}
                  strokeDashoffset={progressOffset}
                />
              </svg>
              <span className="relative text-3xl font-semibold tabular-nums text-foreground">
                {formatTime(remaining)}
              </span>
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              Breathe in… Breathe out…
            </p>
            <p className="mt-4 text-base leading-relaxed text-muted-foreground">
              Take your time. We&apos;ll pick up right where you left off.
            </p>
            <div className="mt-6">
              <Button ref={primaryButtonRef} variant="outline" onClick={handleEarlyReturn}>
                I&apos;m ready, continue
              </Button>
            </div>
          </div>
        )}

        {phase === "welcome-back" && (
          <div className="text-center">
            {/* Adapted-content boundary (AC4): this component does NOT generate or
                fetch the alternative explanation. The Content Adapter (5.2) produced it
                and 5.3 delivered it into the queue; on resume we simply close and let the
                resume flow surface whatever is next (e.g. the inline show_* callout 5.4
                renders, or the section the learner returns to). No LLM call / fetch here. */}
            <p className="text-lg font-medium leading-relaxed text-foreground">
              Welcome back! Ready to continue?
            </p>
            <div className="mt-6">
              <Button ref={primaryButtonRef} onClick={handleDismiss}>
                Continue
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
