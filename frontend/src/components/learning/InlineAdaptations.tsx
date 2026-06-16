"use client";

import { AdaptiveHintCallout } from "@/components/learning/AdaptiveHintCallout";
import { useAdaptationStore } from "@/stores/adaptation-store";
import type { AdaptationAction } from "@/types/ws-messages";

/**
 * InlineAdaptations — thin consumer mounted inline in the lesson content flow.
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
    <AdaptiveHintCallout
      key={active.id}
      adaptation={active}
      onDismiss={() => {
        /* Local UI dismiss only — the callout owns its dismissed/re-access state
           and we deliberately leave the item in the queue (queue-ownership decision). */
      }}
    />
  );
}
