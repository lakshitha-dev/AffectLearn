"use client";

/**
 * Debug overlay for facial-feature capture (Story 4.2 AC #11).
 *
 * Renders only when `NEXT_PUBLIC_AFFECT_DEBUG=1`. Polls the `useMediaPipe`
 * debug ref on a low frequency (250ms) and shows the most recent per-frame
 * latency, mean latency, captured/dropped counters, and current cycle number.
 *
 * This is helpful during pilot setup to spot lighting/positioning issues or
 * frame-budget regressions. Production builds tree-shake this out via the
 * env-flag gate in the lesson page.
 */

import { useEffect, useState } from "react";
import type { DebugMetrics } from "@/hooks/use-media-pipe";

interface AffectDebugOverlayProps {
  debugRef: React.RefObject<DebugMetrics | null>;
}

export function AffectDebugOverlay({ debugRef }: AffectDebugOverlayProps) {
  const [snapshot, setSnapshot] = useState<DebugMetrics | null>(null);

  useEffect(() => {
    const id = setInterval(() => {
      setSnapshot(debugRef.current ? { ...debugRef.current } : null);
    }, 250);
    return () => clearInterval(id);
  }, [debugRef]);

  if (!snapshot) {
    // debugRef is null when NODE_ENV === "production" (metrics not computed per AC #11).
    // Show a clear message rather than rendering nothing, so a NEXT_PUBLIC_AFFECT_DEBUG=1
    // production deploy is obviously broken rather than silently missing.
    return (
      <div className="fixed bottom-4 right-4 z-50 rounded-lg border border-border bg-surface/90 backdrop-blur p-3 text-xs font-mono text-muted-foreground shadow-lg pointer-events-none">
        <div className="text-foreground font-semibold mb-1">Affect debug</div>
        <div>metrics unavailable in production build</div>
      </div>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 rounded-lg border border-border bg-surface/90 backdrop-blur p-3 text-xs font-mono text-muted-foreground shadow-lg pointer-events-none">
      <div className="text-foreground font-semibold mb-1">Affect debug</div>
      <div>cycle: {snapshot.cycleNumber}</div>
      <div>captured: {snapshot.framesCaptured}</div>
      <div>dropped: {snapshot.droppedFrames}</div>
      <div>last frame: {snapshot.lastFrameLatencyMs.toFixed(1)}ms</div>
      <div>mean frame: {snapshot.meanFrameLatencyMs.toFixed(1)}ms</div>
      <div>
        loaded:{" "}
        {snapshot.mediaPipeLoadedAt
          ? new Date(snapshot.mediaPipeLoadedAt).toISOString().slice(11, 19)
          : "—"}
      </div>
    </div>
  );
}
