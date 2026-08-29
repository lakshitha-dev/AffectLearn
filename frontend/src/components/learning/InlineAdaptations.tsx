"use client";

import { useEffect, useState } from "react";

import { AdaptiveHintCallout } from "@/components/learning/AdaptiveHintCallout";
import { cn } from "@/lib/cn";
import { useAdaptationStore } from "@/stores/adaptation-store";
import type { AdaptationAction } from "@/types/ws-messages";

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
 * callback is therefore a non-mutating hook point (left for future research/logging of
 * "hint dismissed"); the queue stays a faithful log for Stories 5.5–5.7, and we never
 * `dismissAdaptation` a non-`show_*` item we do not own.
 */

const INLINE_ACTIONS = new Set<AdaptationAction>([
  "show_hint",
  "show_alternative",
  "show_breakdown",
  "show_encouragement",
]);

export function InlineAdaptations() {
  const adaptationQueue = useAdaptationStore((s) => s.adaptationQueue);

  // Latest inline (`show_*`) adaptation in the queue.
  let active = null;
  for (let i = adaptationQueue.length - 1; i >= 0; i -= 1) {
    const candidate = adaptationQueue[i];
    if (INLINE_ACTIONS.has(candidate.action)) {
      active = candidate;
      break;
    }
  }

  if (!active) return null;

  return <CenteredHint key={active.id} adaptation={active} />;
}

/**
 * Centred, animated hint overlay.
 *
 * Previously this rendered inline BELOW the lesson content, so a delivered hint landed off-screen
 * and a confused learner had to scroll past everything to find the help meant for them.
 *
 * NO DIMMED BACKDROP, unlike `BreakSuggestionCard` (`fixed inset-0 z-50 bg-background/70`). A hint
 * is grounded in the section the learner is reading — dimming the page would hide the very thing
 * the hint refers to. The wrapper is `pointer-events-none` so the lesson stays scrollable and
 * clickable underneath; only the card itself captures clicks. A strong shadow and a ring make it
 * read as floating without blocking anything.
 *
 * z-40 keeps it BELOW the break-suggestion overlay (z-50), so a break card is never obscured.
 */
function CenteredHint({ adaptation }: { adaptation: Parameters<typeof AdaptiveHintCallout>[0]["adaptation"] }) {
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
      className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center p-4"
    >
      <div
        className={cn(
          "pointer-events-auto w-[min(32rem,100%)] rounded-lg bg-background shadow-2xl ring-1 ring-border",
          // Scale + fade entrance. `transition-duration` is neutralised globally under
          // `prefers-reduced-motion: reduce` (globals.css), so this needs no separate guard.
          "transition-[opacity,transform] duration-300 ease-out",
          entered ? "scale-100 opacity-100" : "scale-95 opacity-0",
        )}
      >
        <div className="px-5">
          <AdaptiveHintCallout
            adaptation={adaptation}
            onDismiss={() => {
              /* Local UI dismiss only — the callout owns its dismissed/re-access state
                 and we deliberately leave the item in the queue (queue-ownership decision). */
            }}
          />
        </div>
      </div>
    </div>
  );
}
