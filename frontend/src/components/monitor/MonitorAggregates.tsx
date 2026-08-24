"use client";

/**
 * The Aggregate tab: what the pipeline has actually been DOING over a window.
 *
 * The live stream answers "what is happening now". This answers the calibration question,
 * which is the one that matters in a pilot: at ADAPT_MIN_CONFIDENCE=0.70 the gate withholds on
 * the large majority of cycles, and the only way to tell a correctly-conservative gate from a
 * mis-tuned one is the DISTRIBUTION OF REASONS. Mostly `low_confidence` means the threshold is
 * too high for these models; mostly `cooldown` means the suppression window is too long.
 */

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useMonitorAggregates } from "@/hooks/use-monitor";

const WINDOWS = [
  { value: "1", label: "Last hour" },
  { value: "24", label: "Last 24 hours" },
  { value: "168", label: "Last 7 days" },
];

// Why each reason fires, so the chart is readable without opening the source.
const REASON_HELP: Record<string, string> = {
  state_not_actionable: "detected state is not in ADAPT_STATES (only confused is actionable)",
  low_confidence: "confidence below ADAPT_MIN_CONFIDENCE",
  not_sustained: "state not held for ADAPT_MIN_CONSECUTIVE cycles",
  cooldown: "an intervention fired too recently",
};

const REASON_COLOR: Record<string, string> = {
  state_not_actionable: "#64748b", // slate — the expected default
  low_confidence: "#f59e0b", // amber — consider the threshold
  not_sustained: "#6366f1", // indigo
  cooldown: "#22c55e", // green — the system working as designed
};

function Tile({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "warn";
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-sm">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p
        className={
          tone === "warn"
            ? "mt-1 text-2xl font-semibold text-amber-600 dark:text-amber-400"
            : "mt-1 text-2xl font-semibold text-foreground"
        }
      >
        {value}
      </p>
      {hint ? <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function MonitorAggregates() {
  const [hours, setHours] = useState("24");
  const { data, isPending, isError, error, refetch } = useMonitorAggregates(Number(hours));

  const picker = (
    <Select value={hours} onValueChange={setHours}>
      <SelectTrigger className="w-[170px]" aria-label="Aggregation window">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {WINDOWS.map((w) => (
          <SelectItem key={w.value} value={w.value}>
            {w.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  if (isPending) {
    return (
      <div className="space-y-4">
        <div className="flex justify-end">{picker}</div>
        <div
          role="status"
          aria-label="Loading aggregates"
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
        >
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-border" />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
        <p className="text-sm text-foreground">
          Aggregates unavailable{error ? ": " + (error as Error).message : ""}
        </p>
        <button
          onClick={() => refetch()}
          className="mt-3 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-accent"
        >
          Retry
        </button>
      </div>
    );
  }

  const unknown = Object.entries(data.gateReasonsUnknown ?? {});
  const bars = [...Object.entries(data.gateReasons), ...unknown]
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count);

  const fr = data.interventions.fallbackRate;
  const affect = Object.entries(data.affectCounts ?? {});

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">
            {data.totalEvents.toLocaleString()} events · {data.cycles.toLocaleString()} cycles ·{" "}
            {data.sessions} session{data.sessions === 1 ? "" : "s"}
          </p>
          {data.insufficient_data ? (
            <p className="mt-1 text-[11px] text-amber-600 dark:text-amber-400">
              Limited data — {data.gatedCycles} gated cycle
              {data.gatedCycles === 1 ? "" : "s"} in this window; treat proportions as indicative.
            </p>
          ) : null}
        </div>
        {picker}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          label="Interventions"
          value={String(data.interventions.delivered)}
          hint={data.interventions.perHour + "/hour — designed operating point is ~1.5"}
        />
        <Tile
          label="Cycles"
          value={data.cycles.toLocaleString()}
          hint="one per ~30s of active study"
        />
        <Tile
          label="Fallback rate"
          value={fr == null ? "—" : Math.round(fr * 100) + "%"}
          tone={fr != null && fr > 0.5 ? "warn" : undefined}
          hint={
            fr == null
              ? "no adaptations delivered yet"
              : fr >= 1
                ? "every adaptation was canned, not generated — vLLM unreachable"
                : "share served by the rule-based fallback"
          }
        />
        <Tile
          label="Sessions"
          value={String(data.sessions)}
          hint={"window: " + data.windowHours + "h"}
        />
      </div>

      <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
        <h3 className="text-sm font-semibold text-foreground">Why cycles did not adapt</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Every completed cycle records a gate reason. A healthy pilot is dominated by{" "}
          <code>state_not_actionable</code> — most of the time the learner is simply not confused.
        </p>
        {bars.length === 0 || bars.every((b) => b.count === 0) ? (
          <p className="mt-4 text-sm text-muted-foreground">No gated cycles in this window yet.</p>
        ) : (
          <div className="mt-4 h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={bars}
                layout="vertical"
                margin={{ top: 4, right: 48, bottom: 4, left: 8 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" opacity={0.1} />
                <XAxis type="number" tick={{ fontSize: 10 }} allowDecimals={false} />
                <YAxis type="category" dataKey="reason" tick={{ fontSize: 10 }} width={150} />
                <Tooltip
                  formatter={(v) => [String(v), "cycles"]}
                  labelFormatter={(r) => REASON_HELP[r as string] ?? String(r)}
                />
                <Bar dataKey="count" isAnimationActive={false} radius={[0, 3, 3, 0]}>
                  {bars.map((b) => (
                    <Cell key={b.reason} fill={REASON_COLOR[b.reason] ?? "#94a3b8"} />
                  ))}
                  <LabelList dataKey="count" position="right" style={{ fontSize: 11 }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
        {unknown.length > 0 ? (
          <p className="mt-3 text-[11px] text-amber-600 dark:text-amber-400">
            Unrecognised reason{unknown.length === 1 ? "" : "s"}:{" "}
            {unknown.map(([r]) => r).join(", ")} — this list is out of date with the backend.
          </p>
        ) : null}
      </div>

      <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
        <h3 className="text-sm font-semibold text-foreground">Detections</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Only <code>confused</code> and <code>engaged</code> are detectable — both deployed models
          are binary confusion detectors, so <code>bored</code> and <code>frustrated</code> are
          pinned to zero server-side and are not shown.
        </p>
        <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {affect.length === 0 ? (
            <p className="text-sm text-muted-foreground">No detections in this window.</p>
          ) : (
            affect.map(([state, n]) => (
              <div key={state} className="rounded-md border border-border px-3 py-2">
                <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">
                  {state}
                </dt>
                <dd className="text-lg font-semibold text-foreground">{n.toLocaleString()}</dd>
              </div>
            ))
          )}
        </dl>
      </div>
    </div>
  );
}
