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

export interface ModalityStat {
  n: number;
  min?: number;
  max?: number;
  mean?: number;
  overThreshold?: number;
  reachedThreshold?: boolean;
}

export function FacialPanel({
  data,
  modelAvailable,
  stats,
  threshold,
}: {
  data: Record<string, unknown> | null;
  modelAvailable?: boolean;
  /** Windowed p_confused distribution for this channel, from /monitor/aggregates. */
  stats?: ModalityStat;
  /** Live ADAPT_MIN_CONFIDENCE, so the verdict below tracks configuration. */
  threshold?: number | null;
}) {
  const error = data?.error as string | undefined;
  // `dropped_reasons` used to be discarded by the backend, so this line rendered a permanent
  // "no face: 0 · low confidence: 0" -- a fake zero. It is now forwarded, so absence genuinely
  // means "not reported" and is shown as such rather than as a measurement of zero.
  const reasons = data?.dropped_reasons as
    | { no_face?: number; low_confidence?: number }
    | undefined;
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
            {reasons ? (
              <>
                fallbacks — no face: {reasons.no_face ?? 0} · low confidence:{" "}
                {reasons.low_confidence ?? 0}
              </>
            ) : (
              <span className="italic">fallback breakdown not reported this cycle</span>
            )}
          </p>
          {error ? (
            <p className="rounded bg-red-50 px-2 py-1 text-xs text-red-600 dark:bg-red-900/30 dark:text-red-400">
              inference: {error}
            </p>
          ) : pConfused != null || dist || legacyLevel != null ? (
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
          <FacialCalibration stats={stats} threshold={threshold} />
        </>
      )}
    </div>
  );
}

/**
 * Observed P(confused) range for this channel against the live gate threshold.
 *
 * This exists because a held-out AUC can look respectable while the model's probabilities are too
 * compressed to ever cross a fixed threshold — in which case the channel cannot drive an
 * intervention regardless of how good its ranking is. Every number here is measured over the
 * window, so the warning disappears by itself once the channel starts crossing.
 */
function FacialCalibration({
  stats,
  threshold,
}: {
  stats?: ModalityStat;
  threshold?: number | null;
}) {
  if (!stats || stats.n === 0) return null;

  const t = typeof threshold === "number" ? threshold : null;
  const never = t != null && stats.reachedThreshold === false;

  return (
    <div className="rounded-md border border-border bg-background px-3 py-2">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
        observed P(confused) · {stats.n} cycles
      </p>
      <p className="mt-1 font-mono text-xs text-foreground">
        {stats.min?.toFixed(3)} – {stats.max?.toFixed(3)}
        <span className="text-muted-foreground"> (mean {stats.mean?.toFixed(3)})</span>
        {t != null ? <span className="text-muted-foreground"> · gate {t.toFixed(2)}</span> : null}
      </p>
      {never ? (
        <p className="mt-1.5 text-[11px] text-amber-600 dark:text-amber-400">
          Never reached the gate in this window, so this channel has not triggered an intervention
          on its own — it is contributing as a fusion input only.
        </p>
      ) : (
        <p className="mt-1.5 text-[11px] text-muted-foreground">
          Crossed the gate on {stats.overThreshold ?? 0} of {stats.n} cycles.
        </p>
      )}
    </div>
  );
}
