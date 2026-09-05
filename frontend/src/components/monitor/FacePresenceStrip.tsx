"use client";

/**
 * Per-cycle face presence over the session.
 *
 * The facial panel can only show the LATEST cycle, which cannot answer the question that actually
 * matters when reading an affect trace: was the learner even in front of the camera at the time?
 * A filled cell means a face was detected in enough of that cycle's frames to treat it as an
 * observation; a hollow cell means the cycle was suppressed and the pipeline fell back to
 * behavioural-only.
 *
 * This is the diagnostic for a session where the affect readings look wrong — a run of hollow
 * cells explains it immediately.
 */

import type { FacePresencePoint } from "@/types/monitor";
import { ago } from "./shared";

export function FacePresenceStrip({
  series,
  max = 40,
  stale,
  lastCycleAgeMs,
}: {
  series: FacePresencePoint[];
  /** Most recent N cycles to show. */
  max?: number;
  /**
   * True when the newest cycle is not current. The heading reads "face present" in the present
   * tense, which is correct during a live session and misleading after one ends — a strip of
   * green squares from an hour ago is indistinguishable from a learner sitting there now.
   */
  stale?: boolean;
  lastCycleAgeMs?: number | null;
}) {
  if (series.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No face-presence data yet — reported once a facial cycle arrives.
      </p>
    );
  }

  const shown = series.slice(-max);
  const present = shown.filter((p) => !p.absent).length;
  const pct = Math.round((present / shown.length) * 100);

  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
          {stale ? "face was present" : "face present"} · last {shown.length} cycle
          {shown.length === 1 ? "" : "s"}
          {stale && ago(lastCycleAgeMs) ? (
            <span className="ml-1 normal-case tracking-normal">({ago(lastCycleAgeMs)})</span>
          ) : null}
        </p>
        <p className="font-mono text-xs text-foreground">
          {present}/{shown.length}
          <span className="text-muted-foreground"> ({pct}%)</span>
        </p>
      </div>
      <div className="flex flex-wrap gap-1" role="list" aria-label="Face presence per cycle">
        {shown.map((p, i) => {
          const label =
            `cycle ${p.cycle ?? "?"} — ${p.seen}/${p.captured} frames ` +
            `(${Math.round(p.ratio * 100)}%)` +
            (p.absent ? " — absent, affect suppressed" : "");
          return (
            <span
              key={`${p.t}-${i}`}
              role="listitem"
              title={label}
              aria-label={label}
              className={
                "h-4 w-2.5 rounded-sm border " +
                (p.absent
                  ? "border-amber-500 bg-transparent"
                  : "border-green-600 bg-green-500")
              }
            />
          );
        })}
      </div>
      {present < shown.length ? (
        <p className="mt-2 text-[11px] text-amber-600 dark:text-amber-400">
          {shown.length - present} cycle{shown.length - present === 1 ? "" : "s"} had too few
          face frames to be an observation — facial affect was suppressed for those and the
          pipeline used behavioural signals only.
        </p>
      ) : null}
    </div>
  );
}
