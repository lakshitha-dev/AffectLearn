"use client";

import { useEffect, useRef } from "react";

import { useAdaptationStore } from "@/stores/adaptation-store";

/**
 * IncreaseDifficulty — the Story 5.6 UI-LESS consumer of the `increase_difficulty` action.
 *
 * Per the UX spec the difficulty increase is an INVISIBLE swap: "Content silently replaced
 * with harder variant — No announcement — invisible swap" (UX spec line 675; epics line
 * 1075). So this component renders NOTHING (returns `null`) — there is no callout, card, or
 * toast for this action.
 *
 * INTENTIONALLY NO CONTENT SWAP (Open Question #1): the harder-variant content this action's
 * `metadata.select = "challenge_exercise"` would resolve against does NOT exist yet — the
 * content-variant catalog was deferred from 5.2. This component therefore performs NO real
 * content swap and does NOT fabricate harder content; the actual swap is deferred to the
 * variant catalog (a later content story).
 *
 * LOGGING (AC3): the DURABLE record already exists server-side — `_deliver_adaptation`
 * (`ws.py`) emits an `adaptation_delivered` research event for EVERY delivered adaptation,
 * including `increase_difficulty` (it carries `action` + `variant`). To avoid duplicating
 * that durable log we send ONLY an observability-only client acknowledgement
 * (`interaction: "applied"`) via the optional `onApplied` callback, fired AT MOST ONCE per
 * adaptation id (idempotency guard — AC7) so re-renders never double-log. If `onApplied` is
 * omitted this consumer is a pure no-op acknowledgement.
 *
 * Queue ownership (AC7): does NOT mutate the queue; tracks applied ids locally.
 */

interface IncreaseDifficultyProps {
  /**
   * Optional observability-only client acknowledgement that the invisible swap was applied
   * (FR22 symmetry). The durable record is the server-side `adaptation_delivered` event, so
   * this is safe to omit.
   */
  onApplied?: (adaptationId: string) => void;
}

export function IncreaseDifficulty({ onApplied }: IncreaseDifficultyProps) {
  const adaptationQueue = useAdaptationStore((s) => s.adaptationQueue);
  // Per-id guard so each increase_difficulty item is acknowledged at most once (AC7).
  const appliedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!onApplied) return;
    for (const item of adaptationQueue) {
      if (item.action !== "increase_difficulty") continue;
      if (appliedRef.current.has(item.id)) continue;
      appliedRef.current.add(item.id);
      onApplied(item.id);
    }
  }, [adaptationQueue, onApplied]);

  // Invisible swap (UX spec line 675): renders nothing.
  return null;
}
