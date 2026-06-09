"use client";

/**
 * Debug overlay for behavioral-signal capture (Story 4.3 AC #10).
 *
 * Renders only when `NEXT_PUBLIC_AFFECT_DEBUG=1`. Polls the `useBehavioralSignals`
 * debug ref on a low frequency (250ms) and surfaces the NFR9 data-loss metrics —
 * most importantly `aggregatorMissedTicks`, which must stay < 3 per 30s cycle
 * (3 / 300 expected ticks = 1% loss). Without this panel the metrics were computed
 * but unobservable; this is the AC #10 surfacing.
 *
 * Kept deliberately separate from `AffectDebugOverlay` (facial) so the two Epic-4
 * pipelines can be inspected independently — it is positioned bottom-LEFT to avoid
 * overlapping the facial overlay (bottom-right). Production builds tree-shake this
 * out via the env-flag gate in the lesson page.
 */

import { useEffect, useState } from "react";
import type { BehavioralDebug } from "@/types/behavioral-events";

interface BehavioralDebugOverlayProps {
  debugRef: React.RefObject<BehavioralDebug | null>;
}

export function BehavioralDebugOverlay({
  debugRef,
}: BehavioralDebugOverlayProps) {
  const [snapshot, setSnapshot] = useState<BehavioralDebug | null>(null);

  useEffect(() => {
    const id = setInterval(() => {
      setSnapshot(debugRef.current ? { ...debugRef.current } : null);
    }, 250);
    return () => clearInterval(id);
  }, [debugRef]);

  if (!snapshot) {
    // debugRef is null when NODE_ENV === "production" (metrics not computed per AC #10).
    return (
      <div className="fixed bottom-4 left-4 z-50 rounded-lg border border-border bg-surface/90 backdrop-blur p-3 text-xs font-mono text-muted-foreground shadow-lg pointer-events-none">
        <div className="text-foreground font-semibold mb-1">Behavioral debug</div>
        <div>metrics unavailable in production build</div>
      </div>
    );
  }

  return (
    <div className="fixed bottom-4 left-4 z-50 rounded-lg border border-border bg-surface/90 backdrop-blur p-3 text-xs font-mono text-muted-foreground shadow-lg pointer-events-none">
      <div className="text-foreground font-semibold mb-1">Behavioral debug</div>
      <div>events/s: {snapshot.eventsPerSecond.toFixed(1)}</div>
      <div>agg ticks: {snapshot.aggregatorTickCount}</div>
      <div>
        missed ticks: {snapshot.aggregatorMissedTicks}
        {snapshot.aggregatorMissedTicks >= 3 ? " ⚠ NFR9" : ""}
      </div>
      <div>last dropped: {snapshot.lastCycleDroppedEvents}</div>
      <div>last msg bytes: {snapshot.lastCycleMessageBytes}</div>
    </div>
  );
}
