"use client";

import { ProbBars } from "./ProbBars";
import { behavioralDistribution } from "./prob-labels";

interface Counts {
  mouse_sample_count?: number;
  mouse_click_count?: number;
  keystroke_count?: number;
  scroll_event_count?: number;
}

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border bg-background px-2 py-1.5 text-center">
      <p className="text-base font-semibold text-foreground">{value}</p>
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
    </div>
  );
}

export function BehaviorPanel({ data }: { data: Record<string, unknown> | null }) {
  if (!data) {
    return <p className="text-sm text-muted-foreground">No behavioral cycle yet (sent every ~30s).</p>;
  }
  const counts = (data.event_counts as Counts) ?? {};
  const probs = data.probs as number[] | undefined;
  const idle = !!data.idle;
  const label = data.label as string | undefined;
  const confidence = (data.affect_confidence as number) ?? (data.confidence as number) ?? 0;
  // Read the model identity from the event instead of hardcoding it. The panel said "Bi-LSTM"
  // for a month after the GBDT replaced it; sourcing it from the payload means the next swap
  // updates this label for free.
  const kind = (data.model_kind as string) ?? "model";
  const pConfused = data.p_confused as number | undefined;
  // Correctly-ordered, detectable-only distribution (see prob-labels.ts).
  const dist = behavioralDistribution(probs);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm">
        <span className="font-mono text-[11px] text-muted-foreground">{kind} →</span>
        <span className="font-semibold text-foreground">{label ?? "—"}</span>
        <span className="text-muted-foreground">{(confidence * 100).toFixed(0)}%</span>
        {idle && (
          <span className="rounded-full bg-slate-100 px-2 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            idle window
          </span>
        )}
      </div>
      {pConfused != null && (
        <p className="text-xs text-muted-foreground">
          P(confused) ={" "}
          <span className="font-semibold text-foreground">{pConfused.toFixed(3)}</span>{" "}
          <span className="text-[10px]">— the value the adaptation gate thresholds</span>
        </p>
      )}
      <div className="grid grid-cols-4 gap-2">
        <Count label="mouse" value={counts.mouse_sample_count ?? 0} />
        <Count label="clicks" value={counts.mouse_click_count ?? 0} />
        <Count label="keys" value={counts.keystroke_count ?? 0} />
        <Count label="scroll" value={counts.scroll_event_count ?? 0} />
      </div>
      <div>
        <p className="mb-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
          Classification (softmax) — detectable states only
        </p>
        <ProbBars probs={dist?.probs} labels={dist?.labels} />
      </div>
    </div>
  );
}
