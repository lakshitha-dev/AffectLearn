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
        {/* An idle window is suppressed upstream, so there is no label or confidence to show.
            Rendering the raw absence as "— 0%" read as a broken panel; it is a deliberate
            non-observation and now says so, matching how the facial panel explains its own
            suppression rather than showing an empty distribution. */}
        {idle ? (
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            no interaction this cycle
          </span>
        ) : (
          <>
            <span className="font-semibold text-foreground">{label ?? "—"}</span>
            <span className="text-muted-foreground">{(confidence * 100).toFixed(0)}%</span>
          </>
        )}
      </div>
      {idle && (
        <p className="text-xs text-muted-foreground">
          No mouse, key or scroll activity reached this window, so affect was not inferred. An
          empty window is not evidence that a learner is engaged — the negative class in the
          training corpus absorbs unannotated time, so classifying it would report the learner
          as engaged with high confidence whether or not anyone was there. The feature window is
          still recorded.
        </p>
      )}
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
      {!idle && (
        <div>
          <p className="mb-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
            Classification (softmax) — detectable states only
          </p>
          <ProbBars probs={dist?.probs} labels={dist?.labels} />
        </div>
      )}
    </div>
  );
}
