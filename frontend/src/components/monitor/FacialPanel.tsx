"use client";

import { ProbBars } from "./ProbBars";

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
  const engagement = data?.engagement_level as number | undefined;

  return (
    <div className="space-y-3">
      {modelAvailable === false && (
        <div className="rounded-md border-l-4 border-amber-500 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
          Facial CNN-LSTM model not loaded (<code>cnn_lstm_best.onnx</code> missing). Facial cycles
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
          ) : engagement != null ? (
            <div>
              <p className="text-xs text-muted-foreground">
                engagement level: <span className="font-semibold text-foreground">{engagement}</span>
              </p>
              <div className="mt-1.5">
                <ProbBars probs={probs} labels={["lvl 0", "lvl 1", "lvl 2", "lvl 3"]} />
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
