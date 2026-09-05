"use client";

/**
 * The session at a glance, from the research record.
 *
 * Only quantities that can be computed reliably. Two are deliberately absent: there is no
 * "engagement level" (no model produces a continuous engagement score — `engaged` is the negative
 * class of two binary heads), and no intervention success rate (nothing links a hint to a later
 * state). Both would be easy to display and neither would mean anything.
 */

import type { SessionSummary } from "@/types/monitor";
import { AFFECT_COLORS } from "./shared";

function dur(ms: number | null): string {
  if (ms == null) return "—";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border border-border bg-background px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="font-mono text-lg tabular-nums text-foreground">{value}</p>
      {hint ? <p className="text-[10px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function SessionOverview({ summary, live }: { summary: SessionSummary; live?: boolean }) {
  const total = Object.values(summary.byState).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Metric label="duration" value={dur(summary.durationMs)} hint={live ? "live" : "ended"} />
        <Metric
          label="detections"
          value={String(summary.detectionCount)}
          hint={`of ${summary.cycleCount} cycles`}
        />
        <Metric label="state changes" value={String(summary.stateChangeCount)} />
        <Metric
          label="mean confidence"
          value={summary.meanConfidence != null ? `${Math.round(summary.meanConfidence * 100)}%` : "—"}
        />
        <Metric
          label="interventions"
          value={String(summary.interventionsDelivered)}
          hint={
            summary.deliveriesUnaccounted
              ? `${summary.deliveriesUnaccounted} unaccounted`
              : `${summary.interventionsTriggered} triggered`
          }
        />
        <Metric label="self-reports" value={String(summary.selfReports)} />
      </div>

      {total > 0 ? (
        <div>
          <p className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
            Cycles by detected state
          </p>
          <div className="flex h-3 overflow-hidden rounded">
            {Object.entries(summary.byState).map(([state, n]) => (
              <div
                key={state}
                title={`${state}: ${n} cycles`}
                style={{ width: `${(n / total) * 100}%`, background: AFFECT_COLORS[state] ?? "#64748b" }}
              />
            ))}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
            {Object.entries(summary.byState).map(([state, n]) => (
              <span key={state} className="font-mono text-[10px] text-muted-foreground">
                <span
                  className="mr-1 inline-block h-2 w-2 rounded-sm align-middle"
                  style={{ background: AFFECT_COLORS[state] ?? "#64748b" }}
                />
                {state} {n}
                {summary.dwellMsByState[state] ? ` · ${dur(summary.dwellMsByState[state])}` : ""}
              </span>
            ))}
          </div>
          <p className="mt-1 text-[10px] italic text-muted-foreground">
            `engaged` is the negative class of both detectors — &quot;no confusion found&quot; and
            &quot;no disengagement found&quot; — not a positive reading of engagement.
          </p>
        </div>
      ) : null}
    </div>
  );
}
