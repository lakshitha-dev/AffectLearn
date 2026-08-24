"use client";

import { ProbBars } from "./ProbBars";
import { facialDistribution } from "./prob-labels";

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border bg-background px-2 py-1.5 text-center">
      <p className="text-base font-semibold text-foreground">{value}</p>
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
    </div>
  );
}

export function FacialPanel({
  data,
  modelAvailable,
}: {
  data: Record<string, unknown> | null;
  modelAvailable?: boolean;
}) {
  const error = data?.error as string | undefined;
  const reasons = (data?.dropped_reasons as { no_face?: number; low_confidence?: number }) ?? {};
  const probs = data?.probs as number[] | undefined;
  // The deployed facial model is a BINARY CONFUSION head; `engagement_level` belonged to the
  // superseded 4-level artifact. Prefer the confusion probability and fall back to the raw
  // argmax index only if an older-shaped payload turns up.
  const pConfused = data?.p_confused as number | undefined;
  const label = data?.label as string | undefined;
  const legacyLevel = data?.engagement_level as number | undefined;
  const dist = facialDistribution(probs);

  return (
    <div className="space-y-3">
      {modelAvailable === false && (
        <div className="rounded-md border-l-4 border-amber-500 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
          Facial CNN-LSTM model not loaded. Facial cycles
          degrade to <code>model_unavailable</code> — the capture pipeline still runs.
        </div>
      )}
      {!data ? (
        <p className="text-sm text-muted-foreground">No facial cycle yet (sent every ~30s in adaptive mode).</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2">
            <Count label="captured" value={(data.frames_captured as number) ?? 0} />
            <Count label="dropped" value={(data.dropped_frames as number) ?? 0} />
          </div>
          <p className="text-xs text-muted-foreground">
            drops — no face: {reasons.no_face ?? 0} · low confidence: {reasons.low_confidence ?? 0}
          </p>
          {error ? (
            <p className="rounded bg-red-50 px-2 py-1 text-xs text-red-600 dark:bg-red-900/30 dark:text-red-400">
              inference: {error}
            </p>
          ) : pConfused != null || dist ? (
            <div>
              <p className="text-xs text-muted-foreground">
                {pConfused != null ? (
                  <>
                    P(confused) ={" "}
                    <span className="font-semibold text-foreground">{pConfused.toFixed(3)}</span>
                    {label ? <span className="ml-1">→ {label}</span> : null}
                  </>
                ) : (
                  <>
                    level <span className="font-semibold text-foreground">{legacyLevel}</span>{" "}
                    <span className="text-[10px]">(legacy 4-level payload)</span>
                  </>
                )}
              </p>
              <div className="mt-1.5">
                <ProbBars probs={dist?.probs} labels={dist?.labels} />
              </div>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">no classification this cycle</p>
          )}
        </>
      )}
    </div>
  );
}
