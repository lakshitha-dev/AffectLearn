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
import { exportMonitorCsv, useMonitorAggregates, useMonitorHealth } from "@/hooks/use-monitor";

// 720 is the API's own cap (`hours: int = Query(24, ge=1, le=720)`) and is what the
// data-export page already offers. Without it the deployment record cannot be read
// at the window it is reported over, and a 24-hour view of an instance nobody used
// yesterday is an empty chart rather than a quiet one.
const WINDOWS = [
  { value: "1", label: "Last hour" },
  { value: "24", label: "Last 24 hours" },
  { value: "168", label: "Last 7 days" },
  { value: "720", label: "Last 30 days" },
];

// Why each reason fires, so the chart is readable without opening the source.
// Every reason in `monitor_aggregate_service.GATE_REASONS` needs an entry, or the chart
// draws a labelled bar the reader cannot interpret. The four that were missing here
// are not rare: no_affect and not_eligible are the second and third most frequent
// reasons on the deployed instance.
const REASON_HELP: Record<string, string> = {
  state_not_actionable: "detected state is not in the configured ADAPT_STATES",
  low_confidence: "confidence below ADAPT_MIN_CONFIDENCE",
  not_sustained: "state not held for ADAPT_MIN_CONSECUTIVE cycles",
  cooldown: "an intervention fired too recently",
  no_affect: "the cycle produced no affect reading to act on",
  not_eligible: "the learner is not in the adaptive arm, or the phase does not adapt",
  channel_advisory: "the channel is inferred and logged but not authorised to intervene alone",
  session_cap: "the learner has had this session's full allowance of interventions",
  withheld_random: "cleared every condition, then withheld by the trial draw: the control arm",
};

const REASON_COLOR: Record<string, string> = {
  state_not_actionable: "#64748b", // slate — the expected default
  low_confidence: "#f59e0b", // amber — consider the threshold
  not_sustained: "#6366f1", // indigo
  cooldown: "#22c55e", // green — the system working as designed
  no_affect: "#94a3b8", // lighter slate — nothing to act on, not a decision
  not_eligible: "#94a3b8",
  channel_advisory: "#f59e0b", // amber — a reliability decision, like the floor
  session_cap: "#22c55e", // green — designed restraint
  withheld_random: "#22c55e",
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

export function MonitorAggregates({ sessionId }: { sessionId?: string | null }) {
  const [hours, setHours] = useState("24");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const { data, isPending, isError, error, refetch } = useMonitorAggregates(Number(hours));
  // Thresholds come from the live config, so nothing here states a target from memory.
  const decision = useMonitorHealth().data?.models.decision;

  async function onExport() {
    setExporting(true);
    setExportError(null);
    try {
      await exportMonitorCsv(Number(hours), sessionId);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "export failed");
    } finally {
      setExporting(false);
    }
  }

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
        <div className="flex items-center gap-2">
          <button
            onClick={onExport}
            disabled={exporting}
            className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-50"
          >
            {exporting ? "Exporting…" : "Export CSV"}
          </button>
          {picker}
        </div>
      </div>
      {exportError ? (
        <p className="text-xs text-red-600 dark:text-red-400">Export failed: {exportError}</p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          label="Interventions"
          value={String(data.interventions.delivered)}
          hint={
            data.interventions.perHour +
            "/hour at " +
            [
              decision?.adaptMinConfidence != null ? "conf " + decision.adaptMinConfidence : null,
              decision?.adaptMinConsecutive != null
                ? decision.adaptMinConsecutive + " consecutive"
                : null,
              decision?.adaptCooldownCycles != null
                ? "cooldown " + decision.adaptCooldownCycles
                : null,
            ]
              .filter(Boolean)
              .join(" · ")
          }
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
        <h3 className="text-sm font-semibold text-foreground">Per-modality confidence</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Observed P(confused) per channel against the gate. A channel whose max never reaches the
          threshold cannot have triggered an intervention on its own, whatever its held-out AUC says.
        </p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[520px] text-xs">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th className="py-1.5 text-left font-medium">channel</th>
                <th className="py-1.5 text-right font-medium">n</th>
                <th className="py-1.5 text-right font-medium">min</th>
                <th className="py-1.5 text-right font-medium">max</th>
                <th className="py-1.5 text-right font-medium">mean</th>
                <th className="py-1.5 text-right font-medium">over gate</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.modalityStats ?? {}).map(([name, st]) => (
                <tr key={name} className="border-b border-border last:border-0">
                  <td className="py-1.5 font-mono text-foreground">{name}</td>
                  <td className="py-1.5 text-right">{st.n}</td>
                  <td className="py-1.5 text-right font-mono">{st.min?.toFixed(3) ?? "—"}</td>
                  <td className="py-1.5 text-right font-mono">{st.max?.toFixed(3) ?? "—"}</td>
                  <td className="py-1.5 text-right font-mono">{st.mean?.toFixed(3) ?? "—"}</td>
                  <td
                    className={
                      "py-1.5 text-right " +
                      (st.n > 0 && st.reachedThreshold === false
                        ? "text-amber-600 dark:text-amber-400"
                        : "")
                    }
                  >
                    {st.n === 0 ? "—" : (st.overThreshold ?? 0) + "/" + st.n}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
        <h3 className="text-sm font-semibold text-foreground">Events by type</h3>
        <dl className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(data.eventsByType ?? {})
            .sort((a, b) => b[1] - a[1])
            .map(([t, n]) => (
              <div
                key={t}
                className="flex items-baseline justify-between gap-2 border-b border-border py-1"
              >
                <dt className="font-mono text-[11px] text-muted-foreground">{t}</dt>
                <dd className="text-sm font-semibold text-foreground">{n.toLocaleString()}</dd>
              </div>
            ))}
        </dl>
      </div>

      <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
        <h3 className="text-sm font-semibold text-foreground">Detections</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          {decision?.adaptStates?.length ? (
            <>
              Actionable states are <code>{decision.adaptStates.join(", ")}</code>. A state the
              deployed models cannot emit simply never appears below.
            </>
          ) : (
            <>A state the deployed models cannot emit never appears below.</>
          )}
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
