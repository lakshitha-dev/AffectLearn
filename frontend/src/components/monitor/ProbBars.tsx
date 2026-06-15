"use client";

import { AFFECT_LABELS } from "@/types/monitor";
import { affectColor } from "./shared";

/**
 * Renders a model's softmax distribution as labelled horizontal bars. Defaults to the
 * 4 affect categories (the Bi-LSTM / engagement output order). The argmax is emphasised.
 */
export function ProbBars({
  probs,
  labels = AFFECT_LABELS as readonly string[],
}: {
  probs?: number[] | null;
  labels?: readonly string[];
}) {
  if (!probs || probs.length === 0) {
    return <p className="text-xs text-muted-foreground">no distribution</p>;
  }
  const max = Math.max(...probs);
  return (
    <div className="space-y-1.5">
      {labels.map((label, i) => {
        const v = probs[i] ?? 0;
        const isMax = v === max;
        return (
          <div key={label} className="flex items-center gap-2">
            <span className="w-20 shrink-0 text-[11px] text-muted-foreground">{label}</span>
            <div className="h-3 flex-1 overflow-hidden rounded bg-border/40">
              <div
                className="h-full rounded transition-all"
                style={{
                  width: `${Math.round(v * 100)}%`,
                  background: affectColor(label),
                  opacity: isMax ? 1 : 0.5,
                }}
              />
            </div>
            <span
              className={isMax ? "w-10 text-right text-[11px] font-semibold text-foreground" : "w-10 text-right text-[11px] text-muted-foreground"}
            >
              {(v * 100).toFixed(0)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}
