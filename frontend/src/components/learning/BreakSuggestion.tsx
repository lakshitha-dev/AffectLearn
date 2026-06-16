"use client";

import { BreakSuggestionCard } from "@/components/learning/BreakSuggestionCard";
import { useAdaptationStore } from "@/stores/adaptation-store";

/**
 * BreakSuggestion — thin consumer mounted in the lesson page (Story 5.5).
 *
 * Reads the Story 5.3 `adaptationQueue`, filters to the SINGLE `suggest_break` action,
 * and renders the LATEST matching one as one fixed-position `BreakSuggestionCard`
 * (maximum one overlay visible at a time — UX spec line 1194). Renders nothing when
 * there is no `suggest_break` item (no overlay, no backdrop, no layout shift).
 *
 * It IGNORES every non-`suggest_break` item and leaves them untouched in the queue:
 * the four `show_*` inline actions are consumed by 5.4 (`InlineAdaptations`), and
 * `skip_ahead` / `increase_difficulty` / `simplify` (5.6) and `notification` (5.7) are
 * deferred to those stories. Mirrors `InlineAdaptations.tsx` exactly.
 *
 * Queue ownership: this consumer does NOT mutate the queue. The card owns its
 * suggestion→timer→welcome-back→dismissed lifecycle as LOCAL UI state, so `onDismiss`
 * is a non-mutating hook point (left for future research-logging of "break suggested /
 * taken / declined"); we never `dismissAdaptation` an item this story does not own.
 */

export function BreakSuggestion() {
  const adaptationQueue = useAdaptationStore((s) => s.adaptationQueue);

  // Latest `suggest_break` adaptation in the queue.
  let active = null;
  for (let i = adaptationQueue.length - 1; i >= 0; i -= 1) {
    const candidate = adaptationQueue[i];
    if (candidate.action === "suggest_break") {
      active = candidate;
      break;
    }
  }

  if (!active) return null;

  return (
    <BreakSuggestionCard
      key={active.id}
      adaptation={active}
      onDismiss={() => {
        /* Local UI dismiss only — the card owns its lifecycle and we deliberately
           leave the item in the queue (queue-ownership decision, matches 5.4). */
      }}
    />
  );
}
