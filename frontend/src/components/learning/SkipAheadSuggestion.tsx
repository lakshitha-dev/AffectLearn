"use client";

import { useRef } from "react";

import { SkipAheadCard } from "@/components/learning/SkipAheadCard";
import { useAdaptationStore } from "@/stores/adaptation-store";

/**
 * SkipAheadSuggestion — thin consumer mounted in the lesson page (Story 5.6).
 *
 * Reads the Story 5.3 `adaptationQueue`, filters to the SINGLE `skip_ahead` action, and
 * renders the LATEST matching one as one `SkipAheadCard` (single active suggestion, mirrors
 * `InlineAdaptations` / `BreakSuggestion`). Renders nothing when there is no `skip_ahead`
 * item (no box, no layout shift).
 *
 * It IGNORES every non-`skip_ahead` item and leaves them untouched in the queue: the four
 * `show_*` inline actions are consumed by 5.4 (`InlineAdaptations`), `suggest_break` by 5.5
 * (`BreakSuggestion`), `increase_difficulty` by the inline callout (`InlineAdaptations`)
 * (5.6), and `simplify` (5.4-adjacent) / `notification` (5.7) are deferred to those stories.
 *
 * NAVIGATION (AC2): on accept the card advances the content view to the NEXT section. We use
 * a passed `onSkip` callback from the lesson page (rather than DOM scrolling inside the
 * consumer) because the page already owns `handleSectionNav` + the section index list — the
 * callback is the cleaner, testable seam and reuses the EXACT same scroll-based mechanism as
 * the prev/next buttons. "harder section / challenge exercise" degrades to "next section"
 * until the content-variant catalog lands (Open Question #1).
 *
 * LOGGING (AC4/FR22): on accept/dismiss the consumer calls `onInteraction` (a thin wrapper
 * around the WS `send`) so the backend logs the interaction for the Learner Profiler. The
 * log fires AT MOST ONCE per adaptation id (idempotency guard) so React re-renders / store
 * updates never emit duplicate research events.
 *
 * Queue ownership (AC7): local UI state only — this consumer does NOT mutate the queue
 * (no `dismissAdaptation`), keeping the queue a faithful research log (matches 5.4/5.5).
 */

export type SkipInteraction = "accepted" | "dismissed";

interface SkipAheadSuggestionProps {
  /** Advance the content view to the next section (lesson page wires this to handleSectionNav). */
  onSkip: () => void;
  /** Log the accept/dismiss interaction upstream (FR22). */
  onInteraction: (adaptationId: string, interaction: SkipInteraction) => void;
}

export function SkipAheadSuggestion({ onSkip, onInteraction }: SkipAheadSuggestionProps) {
  const adaptationQueue = useAdaptationStore((s) => s.adaptationQueue);
  // Per-id guard so accept/dismiss is logged at most once per adaptation (AC7).
  const loggedRef = useRef<Set<string>>(new Set());

  // Latest `skip_ahead` adaptation in the queue.
  let active = null;
  for (let i = adaptationQueue.length - 1; i >= 0; i -= 1) {
    const candidate = adaptationQueue[i];
    if (candidate.action === "skip_ahead") {
      active = candidate;
      break;
    }
  }

  if (!active) return null;

  const log = (id: string, interaction: SkipInteraction) => {
    if (loggedRef.current.has(id)) return;
    loggedRef.current.add(id);
    onInteraction(id, interaction);
  };

  return (
    <SkipAheadCard
      key={active.id}
      adaptation={active}
      onAccept={() => {
        log(active.id, "accepted");
        // Best-available navigation: advance to the next section (graceful no-op at the
        // end — the lesson page's handleSectionNav guards the out-of-range index).
        onSkip();
      }}
      onDismiss={() => {
        log(active.id, "dismissed");
        /* Local UI dismiss only — the card owns its lifecycle and we deliberately leave
           the item in the queue (queue-ownership decision, matches 5.4/5.5). */
      }}
    />
  );
}
