"use client";

import { useEffect, useRef, useState } from "react";
import { FastForward, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { useReducedMotion } from "@/hooks/use-reduced-motion";
import type { Adaptation } from "@/stores/adaptation-store";

/**
 * SkipAheadCard — the Story 5.6 accept/dismiss suggestion for the `skip_ahead` action.
 *
 * Rendered when the learner is detected bored on familiar material (5.1 chooses
 * `skip_ahead`). It is a gentle, in-flow inline suggestion (NOT a blocking modal — UX
 * spec "Intervene, Don't Interrupt" / "Never Block Learning", lines 72/188/802) with two
 * controls:
 *   - accept ("Skip ahead", primary)  → `onAccept()`  (advances the section in the parent)
 *   - dismiss ("Not now", ghost; + a top-right X) → `onDismiss()`
 *
 * NAVIGATION SCOPE (Open Question #1): accepting "skips to the challenge exercise" by
 * advancing to the NEXT existing section via the lesson page's scroll-based nav. The real
 * content-variant catalog (`metadata.select = "next_section"`) does NOT exist yet (deferred
 * from 5.2), so "harder section / challenge exercise" degrades to "advance to the next
 * section". This component does NOT fabricate harder content — it only renders the
 * suggestion and reports accept/dismiss; the parent owns the actual navigation.
 *
 * Copy: the epic-spec'd learner-facing line "Looks like you've got this — skip to the
 * challenge exercise?" (epics line 1070), NOT the backend framing `text` (Dev Notes).
 *
 * Reuse (do NOT reinvent): the `AdaptiveHintCallout` shell idiom (3px left border on
 * `--primary-soft`, role/aria-label, focusable, CSS-driven fade-in so the global
 * `prefers-reduced-motion` rule clamps it for free), the scoped-Escape idiom (so the
 * lesson page's window Escape→focus-mode handler does NOT fire), and `useReducedMotion()`
 * for the JS-timed fade-out only.
 */

const FADE_OUT_MS = 200;

const SKIP_AHEAD_COPY = "Looks like you've got this — skip to the challenge exercise?";

interface SkipAheadCardProps {
  adaptation: Adaptation;
  /** Accept: advance the content view to the next section (parent owns the nav). */
  onAccept: () => void;
  /** Dismiss: hide the suggestion; flow continues uninterrupted. */
  onDismiss: () => void;
}

export function SkipAheadCard({ adaptation, onAccept, onDismiss }: SkipAheadCardProps) {
  const reducedMotion = useReducedMotion();

  // Local UI state — leaves the queue untouched (queue-ownership decision, matches 5.4/5.5).
  const [gone, setGone] = useState(false);
  const [leaving, setLeaving] = useState(false);
  // Enter animation: start invisible, flip to visible after a rAF so the CSS transition runs.
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Guard so a rapid double accept/dismiss only fires the callback once.
  const actedRef = useRef(false);

  useEffect(() => {
    const raf = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const hide = (after: () => void) => {
    if (leaving || gone || actedRef.current) return;
    actedRef.current = true;
    setLeaving(true);
    const finish = () => {
      setLeaving(false);
      setGone(true);
      after();
    };
    if (reducedMotion) {
      finish();
      return;
    }
    timerRef.current = setTimeout(finish, FADE_OUT_MS);
  };

  const handleAccept = () => hide(onAccept);
  const handleDismiss = () => hide(onDismiss);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      // Mirror AdaptiveHintCallout:124-133 — stopPropagation halts React bubbling and
      // stopImmediatePropagation halts the native event before it reaches window-level
      // listeners (the lesson page's focus-mode Escape handler), so only this card closes.
      event.stopPropagation();
      event.nativeEvent.stopImmediatePropagation();
      handleDismiss();
    }
  };

  if (gone) return null;

  return (
    <div
      role="complementary"
      aria-label="Skip ahead suggestion"
      tabIndex={0}
      onKeyDown={handleKeyDown}
      className={cn(
        "relative my-6 rounded-r-lg border-l-[3px] border-primary bg-primary-soft px-5 py-4",
        "transition-[opacity,transform] duration-300 ease-out",
        leaving
          ? "opacity-0 translate-y-1 duration-200"
          : visible
            ? "opacity-100 translate-y-0"
            : "opacity-0 translate-y-2",
      )}
    >
      <button
        type="button"
        onClick={handleDismiss}
        aria-label="Dismiss suggestion"
        className="absolute right-3 top-3 rounded p-1 text-muted-foreground transition-colors hover:bg-border"
      >
        <X className="h-4 w-4" />
      </button>

      <div className="pr-6">
        <p className="text-base leading-relaxed text-foreground">{SKIP_AHEAD_COPY}</p>
        <div className="mt-3 flex items-center gap-2">
          <Button type="button" size="sm" onClick={handleAccept}>
            <FastForward className="h-4 w-4" aria-hidden="true" />
            Skip ahead
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={handleDismiss}>
            Not now
          </Button>
        </div>
      </div>
    </div>
  );
}
