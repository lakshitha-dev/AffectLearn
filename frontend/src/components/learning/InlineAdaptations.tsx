"use client";

import { useEffect, useState } from "react";

import { AdaptiveHintCallout } from "@/components/learning/AdaptiveHintCallout";
import { cn } from "@/lib/cn";
import { type Adaptation, useAdaptationStore } from "@/stores/adaptation-store";
import type { AdaptationAction, HelpRequestKind } from "@/types/ws-messages";

/**
 * InlineAdaptations — thin consumer rendering the active `show_*` adaptation.
 *
 * NAME IS HISTORICAL: this was mounted inline in the lesson content flow, which put a delivered
 * hint below the whole page. It now renders as a fixed bottom-right card (see the render body).
 * The name is kept so imports and the Story 5.4 references stay stable; "inline" here means
 * "the inline `show_*` action family", not the layout.
 *
 * Reads the Story 5.3 `adaptationQueue`, filters to the four learner-facing inline
 * `show_*` actions, and renders the LATEST matching one as a single
 * `AdaptiveHintCallout` (single active callout policy for 5.4 — see AC8 / Open
 * Question #2). Non-`show_*` items (`suggest_break`, `skip_ahead`,
 * `increase_difficulty`, `simplify`, `notification`) are IGNORED and left untouched
 * in the queue for Stories 5.5–5.7 to consume.
 *
 * Renders nothing when there is no matching inline adaptation (no empty box, no
 * layout shift).
 *
 * Queue ownership: this consumer does NOT mutate the queue. Dismissal is owned
 * entirely as LOCAL UI state INSIDE the callout (so its "Show hint" re-access can
 * restore the exact same content without the consumer unmounting it). The `onDismiss`
 * callback is therefore a non-mutating hook point, now wired to report a `dismissed`
 * interaction to the research record; the queue stays a faithful log for Stories 5.5–5.7,
 * and we never `dismissAdaptation` a non-`show_*` item we do not own.
 */

/**
 * What renders in the inline callout.
 *
 * `simplify` and `increase_difficulty` were added once both became generative text actions.
 * Before that neither reached a learner at all: `simplify` had no consumer anywhere in the
 * routing matrix, so a frustrated learner on a degraded LLM got silence; `increase_difficulty`
 * had a consumer that rendered `null`, because the harder-content catalogue it was written to
 * select from does not exist. Both now produce prose grounded in the section, which is exactly
 * what this surface displays.
 */
const INLINE_ACTIONS = new Set<AdaptationAction>([
  "show_hint",
  "show_alternative",
  "show_breakdown",
  "show_encouragement",
  "simplify",
  "increase_difficulty",
  "show_video",
]);

/**
 * What counts as ASSISTANCE when a quiz answer is attributed to preceding help.
 *
 * Deliberately narrower than INLINE_ACTIONS. `increase_difficulty` renders on the same surface
 * but is the opposite intervention: it asks the learner a harder question rather than helping
 * them with this one. Counting it as assistance would put "was the learner helped before
 * answering" and "was the learner challenged before answering" in the same column, and the
 * research question that column exists to answer could no longer be asked of it.
 */
const ASSISTANCE_ACTIONS = new Set<AdaptationAction>([
  "show_hint",
  "show_alternative",
  "show_breakdown",
  "show_encouragement",
  "simplify",
  "show_video",
]);

/**
 * The inline adaptation currently on screen, or null.
 *
 * Exported because a second caller needs the SAME answer: when a learner submits a quiz answer,
 * the lesson page attaches the active hint's `adaptationId` so the server can record what
 * happened after the help was shown. If that caller re-implemented "the latest inline item in
 * the queue", the two could silently disagree — the page attributing an answer to a hint the
 * learner was never looking at — and nothing would fail loudly.
 *
 * Pure and queue-order dependent: the LAST matching item wins, matching the single-active-callout
 * policy this component renders under.
 */
export function activeInlineAdaptation(
  queue: readonly Adaptation[],
): Adaptation | null {
  return latestMatching(queue, ASSISTANCE_ACTIONS);
}

/** The item this component should DISPLAY — the wider set, including the challenge action. */
export function activeRenderableAdaptation(
  queue: readonly Adaptation[],
): Adaptation | null {
  return latestMatching(queue, INLINE_ACTIONS);
}

/**
 * Whether this adaptation has anything to say.
 *
 * Every action rendered on this surface is GENERATIVE — the whole item is the text. With an
 * empty or whitespace-only `text` the callout still drew its full shell: left border, label
 * ("Let's break this down"), dismiss button, and a blank body. That reads as a rendering fault
 * to the learner, and it is indistinguishable from one when reported. It is really an
 * adaptation that arrived with no content, which is a backend outcome and belongs in the
 * pipeline monitor, not on a card.
 *
 * `show_encouragement` is exempt: its callout carries standalone fallback copy, so an empty one
 * still delivers the encouragement it was chosen for.
 */
function hasRenderableText(adaptation: Adaptation): boolean {
  if (adaptation.action === "show_encouragement") return true;
  return (adaptation.text ?? "").trim().length > 0;
}

function latestMatching(
  queue: readonly Adaptation[],
  actions: ReadonlySet<AdaptationAction>,
): Adaptation | null {
  for (let i = queue.length - 1; i >= 0; i -= 1) {
    const candidate = queue[i];
    if (actions.has(candidate.action) && hasRenderableText(candidate)) return candidate;
  }
  return null;
}

export function InlineAdaptations({
  onInteraction,
  onRequest,
  sectionId,
}: {
  /**
   * Report a learner response to the research record. Optional so existing mounts and tests keep
   * working; where it is not supplied the dismissal is local-only, exactly as before.
   */
  onInteraction?: (payload: {
    adaptation_id: string;
    action: AdaptationAction;
    interaction: "dismissed" | "accepted";
  }) => void;
  /**
   * The learner asked for the next step from the card on screen. Optional: without it the card
   * shows no response buttons, exactly as before.
   */
  onRequest?: (payload: {
    request: HelpRequestKind;
    adaptation_id: string;
    action: AdaptationAction;
  }) => void;
  /** The section on screen; enables "Watch a video explanation" on confusion cards. */
  sectionId?: string;
} = {}) {
  const adaptationQueue = useAdaptationStore((s) => s.adaptationQueue);

  const active = activeRenderableAdaptation(adaptationQueue);
  if (!active) return null;

  return (
    <CenteredHint
      key={active.id}
      adaptation={active}
      onDismiss={() =>
        onInteraction?.({
          adaptation_id: active.id,
          action: active.action,
          interaction: "dismissed",
        })
      }
      onGotIt={() =>
        onInteraction?.({
          adaptation_id: active.id,
          action: active.action,
          interaction: "accepted",
        })
      }
      sectionId={sectionId}
      onRequest={
        onRequest
          ? (request) =>
              onRequest({ request, adaptation_id: active.id, action: active.action })
          : undefined
      }
    />
  );
}

/**
 * Bottom-centred, animated hint sheet.
 *
 * Position history, because it has moved twice for concrete reasons:
 *   1. Inline below the lesson content — a delivered hint landed off-screen entirely.
 *   2. Vertically centred — visible, but it sat on top of the code block and exercise the hint was
 *      explaining. On a laptop viewport it covered most of the reading area.
 *   3. Bottom-centred (here) — horizontally centred so it is unmissable, anchored to the bottom so
 *      the material above it stays readable while the learner acts on the advice.
 *
 * NO DIMMED BACKDROP, unlike `BreakSuggestionCard` (`fixed inset-0 z-50 bg-background/70`). A hint
 * is grounded in the section the learner is reading — dimming the page hides the very thing the
 * hint refers to. The wrapper is `pointer-events-none` so the lesson stays scrollable and
 * clickable underneath; only the card itself captures clicks.
 *
 * z-40 keeps it BELOW the break-suggestion overlay (z-50), so a break card is never obscured.
 */
function CenteredHint({
  adaptation,
  onDismiss,
  onGotIt,
  onRequest,
  sectionId,
}: {
  adaptation: Parameters<typeof AdaptiveHintCallout>[0]["adaptation"];
  /** Reports the dismissal upstream; the callout still owns its own local dismissed state. */
  onDismiss?: () => void;
  onGotIt?: () => void;
  onRequest?: (kind: HelpRequestKind) => void;
  sectionId?: string;
}) {
  // Deferred by one frame so the browser paints the "before" state first; without this the
  // element mounts already-visible and the transition never runs.
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    const raf = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex justify-center p-4"
    >
      <div
        className={cn(
          "pointer-events-auto w-[min(34rem,100%)] rounded-lg bg-background shadow-2xl ring-1 ring-border",
          // Bounded height with its own scrollbar. A `show_breakdown` can run to several steps;
          // unbounded it overflowed the card and the last line was clipped mid-sentence, which
          // looked like a truncation bug. The card scrolls, the page never does.
          "max-h-[45vh] overflow-y-auto",
          // Slide-up + fade entrance. `transition-duration` is neutralised globally under
          // `prefers-reduced-motion: reduce` (globals.css), so this needs no separate guard.
          "transition-[opacity,transform] duration-300 ease-out",
          entered ? "translate-y-0 opacity-100" : "translate-y-4 opacity-0",
        )}
      >
        <div className="px-5">
          <AdaptiveHintCallout
            adaptation={adaptation}
            onGotIt={onGotIt}
            onRequest={onRequest}
            sectionId={sectionId}
            onDismiss={() => {
              // Queue ownership is unchanged: the callout still owns its own dismissed/re-access
              // state and the item stays in the queue. What is new is that the dismissal is
              // REPORTED. Hints were previously the only action type that recorded nothing at
              // all -- skip_ahead and increase_difficulty both reported -- so "was the hint
              // engaged with or waved away" had no answer for the content the study is about.
              onDismiss?.();
            }}
          />
        </div>
      </div>
    </div>
  );
}
