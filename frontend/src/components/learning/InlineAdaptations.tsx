"use client";

import { AdaptiveHintCallout } from "@/components/learning/AdaptiveHintCallout";
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

  return (
    // Fixed bottom-right, NOT in the content flow. This component was mounted below the lesson
    // body, so a delivered hint landed off-screen and a confused learner had to scroll past
    // everything to find the help meant for them.
    //
    // Deliberately NOT a blocking modal like `BreakSuggestionCard` (`fixed inset-0` + dimmed
    // backdrop): a hint is grounded in the section the learner is reading, and dimming that
    // section hides the very thing the hint refers to. It would also undo the adaptation-gate
    // work whose whole purpose was to stop interrupting learners.
    //
    // z-40 keeps it BELOW the break-suggestion overlay (z-50) so a break card is never obscured.
    // `aria-live="polite"` announces a hint that arrives outside the viewport instead of it
    // appearing silently; `pointer-events-none` on the wrapper keeps the rest of the page
    // clickable, with pointer events restored on the card itself.
    <div
      aria-live="polite"
      className="pointer-events-none fixed bottom-4 right-4 z-40 w-[min(24rem,calc(100vw-2rem))]"
    >
      <div className="pointer-events-auto">
        <AdaptiveHintCallout
          key={active.id}
          adaptation={active}
          onDismiss={() => {
            /* Local UI dismiss only — the callout owns its dismissed/re-access state
               and we deliberately leave the item in the queue (queue-ownership decision). */
          }}
        />
      </div>
    </div>
  );
}
