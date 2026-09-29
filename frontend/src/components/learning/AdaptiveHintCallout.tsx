"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, X } from "lucide-react";

import { cn } from "@/lib/cn";
import { useReducedMotion } from "@/hooks/use-reduced-motion";
import { VideoHelp } from "@/components/learning/VideoHelp";
import type { Adaptation } from "@/stores/adaptation-store";
import type { HelpRequestKind } from "@/types/ws-messages";

/**
 * AdaptiveHintCallout — the FIRST visual consumer of the Story 5.3 `adaptationQueue`.
 *
 * Renders one inline adaptation as a gentle, in-flow callout (never a modal / popup /
 * toast). It covers exactly the four learner-facing `show_*` actions:
 *   - `show_hint`          → blue 3px left-border callout on `--primary-soft`
 *   - `show_alternative`   → same shell, a distinct (`--surface`) shade ("a different lens")
 *   - `show_breakdown`     → same shell, an expandable numbered `<ol>` (defaults expanded)
 *   - `show_encouragement` → minimal warm inline text, NO box, NO border
 *
 * The break card (`suggest_break`, 5.5), skip/difficulty UI (5.6) and notification
 * toasts (5.7) are OUT of scope — this component never handles those actions.
 *
 * Animation: enter (300ms fade/slide-down) and exit (200ms fade-out) are driven by
 * CSS/Tailwind transition utilities, so the global `@media (prefers-reduced-motion: reduce)`
 * rule in `globals.css` clamps them to ~instant for free. The only JS timing is the
 * 200ms delay before the dismissed/"Show hint" state is shown; that delay is skipped
 * when `useReducedMotion()` is true so reduced-motion users get an instant dismiss.
 *
 * Queue ownership (Open Question #1): this component manages its visible/dismissed UI
 * state LOCALLY so the "Show hint" re-access can restore identical content. It never
 * mutates the queue itself; the parent consumer owns any `dismissAdaptation` call and
 * only ever for the `show_*` item it rendered. (See Dev Notes "Queue ownership".)
 */

const FADE_OUT_MS = 200;

type CalloutVariant =
  | "hint"
  | "alternative"
  | "breakdown"
  | "encouragement"
  | "simpler"
  | "challenge"
  | "video";

// Must cover every action `InlineAdaptations` routes here. `simplify` and `increase_difficulty`
// were renderable but missing from this map, so both fell through the `?? "hint"` below and were
// introduced as "Here's another way to think about this…" — wrong for a simplification, and
// badly wrong for a challenge offered to a learner who was bored rather than stuck.
const VARIANT_BY_ACTION: Record<string, CalloutVariant> = {
  show_hint: "hint",
  show_alternative: "alternative",
  show_breakdown: "breakdown",
  show_encouragement: "encouragement",
  simplify: "simpler",
  increase_difficulty: "challenge",
  show_video: "video",
};

const VARIANT_LABEL: Record<CalloutVariant, string> = {
  hint: "Here's another way to think about this…",
  alternative: "Another way to look at this",
  breakdown: "Let's break this down",
  encouragement: "",
  simpler: "Put more simply",
  // An invitation, not help: a bored learner is under-challenged, not struggling.
  challenge: "Ready for a harder one?",
  // The last confusion rung: the Pedagogical agent's Video sub-agent picked this video.
  video: "Watch it worked through",
};

interface AdaptiveHintCalloutProps {
  adaptation: Adaptation;
  /** Called when the learner fully dismisses (after the fade-out completes). */
  onDismiss: () => void;
  /**
   * The learner asked for the next step from this card. When supplied, the card shows its
   * response buttons; when absent (older mounts, tests) it renders exactly as before.
   */
  onRequest?: (kind: HelpRequestKind) => void;
  /** The learner said the card worked ("Got it"). Reported, then the card is dismissed. */
  onGotIt?: () => void;
  /**
   * The section this card is about. When supplied, confusion cards offer "Watch a video
   * explanation" (the Video Resource Agent); when absent, no video button is shown.
   */
  sectionId?: string;
}

/** Cards about NOT understanding something, where a video explanation is a sensible next step. */
const VIDEO_VARIANTS: ReadonlySet<CalloutVariant> = new Set([
  "hint",
  "alternative",
  "breakdown",
  "simpler",
  "video",
]);

/**
 * The two responses each variant offers. A help card asks whether it worked; a challenge card,
 * shown to a learner who was under-challenged, offers help or a way forward instead.
 */
const RESPONSES: Partial<
  Record<CalloutVariant, { primary: string; secondary: string; request: HelpRequestKind }>
> = {
  hint: { primary: "Got it", secondary: "Still stuck", request: "still_stuck" },
  alternative: { primary: "Got it", secondary: "Still stuck", request: "still_stuck" },
  breakdown: { primary: "Got it", secondary: "Still stuck", request: "still_stuck" },
  simpler: { primary: "Got it", secondary: "Still stuck", request: "still_stuck" },
  video: { primary: "Got it", secondary: "Still stuck", request: "still_stuck" },
  challenge: { primary: "Give me a hint", secondary: "I'd rather move on", request: "move_on" },
};

/** Split breakdown text into steps; degrades gracefully to a single step. */
function parseSteps(text: string | undefined): string[] {
  if (!text) return [];
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*(?:\d+[.)]|[-*•])\s*/, "").trim())
    .filter((line) => line.length > 0);
  if (lines.length > 0) return lines;
  const trimmed = text.trim();
  return trimmed ? [trimmed] : [];
}

export function AdaptiveHintCallout({
  adaptation,
  onDismiss,
  onRequest,
  onGotIt,
  sectionId,
}: AdaptiveHintCalloutProps) {
  const reducedMotion = useReducedMotion();
  const variant = VARIANT_BY_ACTION[adaptation.action] ?? "hint";

  // Local UI state — leaves the queue untouched (queue ownership decision).
  const [dismissed, setDismissed] = useState(false);
  // Drives the fade-out before the dismissed affordance replaces the callout.
  const [leaving, setLeaving] = useState(false);
  // Drives the enter (fade-in) animation: starts false so the component renders at
  // opacity-0 on mount; a rAF-deferred effect flips it to true, triggering the
  // 300ms CSS transition (AC1 / Success Criteria: "fades in over 300ms ease").
  const [visible, setVisible] = useState(false);
  const [expanded, setExpanded] = useState(true);
  // Set once the learner has asked for the next step, so the buttons cannot fire twice while the
  // agents work; the next card replaces this one when it arrives.
  const [requested, setRequested] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Trigger enter animation on mount (opacity-0 → opacity-100 via CSS transition).
  useEffect(() => {
    const raf = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const handleDismiss = () => {
    // Guard: if already leaving or dismissed, ignore (prevents double-dismiss race
    // where a rapid second click would set a second timer and call onDismiss twice).
    if (leaving || dismissed) return;
    setLeaving(true);
    const finish = () => {
      setLeaving(false);
      setDismissed(true);
      onDismiss();
    };
    if (reducedMotion) {
      finish();
      return;
    }
    timerRef.current = setTimeout(finish, FADE_OUT_MS);
  };

  const handleRestore = () => {
    setDismissed(false);
    setLeaving(false);
    // Re-trigger the enter animation when the callout is restored.
    setVisible(false);
    requestAnimationFrame(() => setVisible(true));
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      // stopPropagation stops React synthetic bubbling; stopImmediatePropagation
      // stops the underlying native event from reaching window-level listeners
      // (e.g. the lesson page's focus-mode toggle), so only the callout dismisses.
      event.stopPropagation();
      event.nativeEvent.stopImmediatePropagation();
      handleDismiss();
    }
  };

  if (dismissed) {
    return (
      <div role="complementary" aria-label="Learning hint" className="my-6">
        <button
          type="button"
          data-track="adaptation-restore"
          onClick={handleRestore}
          className="text-sm text-muted-foreground underline-offset-2 hover:text-primary hover:underline"
        >
          Show hint
        </button>
      </div>
    );
  }

  const body = adaptation.text;
  const steps = variant === "breakdown" ? parseSteps(body) : [];

  // Encouragement: minimal inline warm text, no box, no border (AC4).
  if (variant === "encouragement") {
    return (
      <div
        ref={containerRef}
        role="complementary"
        aria-label="Learning hint"
        tabIndex={0}
        onKeyDown={handleKeyDown}
        className={cn(
          "relative my-6 pr-8 transition-opacity duration-300 ease-out",
          leaving ? "opacity-0 duration-200" : visible ? "opacity-100" : "opacity-0",
        )}
      >
        <p className="text-sm italic text-muted-foreground">
          {body ?? "Nice work on that section."}
        </p>
        <DismissButton onClick={handleDismiss} />
      </div>
    );
  }

  // Boxed variants share the left-border shell; alternative uses a distinct shade.
  const shellShade = variant === "alternative" ? "bg-surface" : "bg-primary-soft";

  return (
    <div
      ref={containerRef}
      data-track="adaptation-card"
      role="complementary"
      aria-label="Learning hint"
      tabIndex={0}
      onKeyDown={handleKeyDown}
      className={cn(
        "relative my-6 rounded-r-lg border-l-[3px] border-primary px-5 py-4",
        "transition-[opacity,transform] duration-300 ease-out",
        shellShade,
        leaving
            ? "opacity-0 translate-y-1 duration-200"
            : visible
              ? "opacity-100 translate-y-0"
              : "opacity-0 translate-y-2",
      )}
    >
      <DismissButton onClick={handleDismiss} />

      {variant === "breakdown" ? (
        <div className="pr-6">
          <button
            type="button"
            data-track="adaptation-expand"
            aria-expanded={expanded}
            onClick={() => setExpanded((prev) => !prev)}
            className="flex items-center gap-1.5 text-sm font-medium text-primary"
          >
            <ChevronDown
              className={cn("h-4 w-4 transition-transform", expanded ? "" : "rotate-90")}
              aria-hidden="true"
            />
            {VARIANT_LABEL.breakdown}
          </button>
          {expanded && (
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-base leading-relaxed text-foreground">
              {steps.length > 0 ? (
                steps.map((step, idx) => <li key={idx}>{step}</li>)
              ) : (
                <li>{body}</li>
              )}
            </ol>
          )}
        </div>
      ) : (
        <div className="pr-6">
          <p className="text-sm font-medium text-primary">{VARIANT_LABEL[variant]}</p>
          <p className="mt-1 text-base leading-relaxed text-foreground">{body}</p>
        </div>
      )}

      {onRequest && RESPONSES[variant] ? (
        <ResponseButtons
          labels={RESPONSES[variant]!}
          requested={requested}
          onPrimary={() => {
            if (variant === "challenge") {
              // "Give me a hint" on a challenge: the learner is now stuck, not bored.
              setRequested(true);
              onRequest("still_stuck");
              return;
            }
            onGotIt?.();
            handleDismiss();
          }}
          onSecondary={() => {
            setRequested(true);
            onRequest(RESPONSES[variant]!.request);
          }}
        />
      ) : null}

      {sectionId && VIDEO_VARIANTS.has(variant) ? (
        <div className="pr-6">
          <VideoHelp
            sectionId={sectionId}
            adaptationId={adaptation.id}
            hintText={body}
            highlighted={requested}
            delivered={variant === "video" ? adaptation.video : undefined}
            autoOpen={variant === "video"}
          />
        </div>
      ) : null}
    </div>
  );
}

function ResponseButtons({
  labels,
  requested,
  onPrimary,
  onSecondary,
}: {
  labels: { primary: string; secondary: string };
  requested: boolean;
  onPrimary: () => void;
  onSecondary: () => void;
}) {
  if (requested) {
    return (
      <p role="status" className="mt-3 text-sm text-muted-foreground">
        Finding another way to help…
      </p>
    );
  }
  return (
    <div className="mt-3 flex flex-wrap gap-2 pr-6">
      <button
        type="button"
        data-track="adaptation-primary"
        onClick={onPrimary}
        className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
      >
        {labels.primary}
      </button>
      <button
        type="button"
        data-track="adaptation-secondary"
        onClick={onSecondary}
        className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-border"
      >
        {labels.secondary}
      </button>
    </div>
  );
}

function DismissButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      data-track="adaptation-dismiss"
      onClick={onClick}
      aria-label="Dismiss hint"
      className="absolute right-3 top-3 rounded p-1 text-muted-foreground transition-colors hover:bg-border"
    >
      <X className="h-4 w-4" />
    </button>
  );
}
