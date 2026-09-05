"use client";

/**
 * How the learner's detected state moved through the session.
 *
 * Sourced from the DATABASE (`/monitor/session/{id}`), not the live stream. The stream keeps a
 * 500-slot in-process ring — about seven to ten cycles, and nothing after a restart — so it cannot
 * answer "when did this change" for any session longer than a few minutes.
 *
 * WHAT IS DERIVED, AND WHY IT IS DERIVED SERVER-SIDE
 *
 * The system records a state per cycle and never a duration, so every "held for 90s" here is
 * arithmetic over consecutive cycles. That arithmetic lives in `session_history_service` so this
 * view and the CSV export cannot drift apart.
 *
 * Two conventions worth knowing when reading a row:
 *   - A run that follows an OBSERVATION GAP has no `from`. The learner was not observed in
 *     between, so the previous state did not continue — it ended when observation stopped.
 *   - The final run has no duration. The session may still be open, and the alternative is to
 *     invent an end time.
 */

import { useState } from "react";

import type { SessionCycle, StateChange } from "@/types/monitor";
import { AFFECT_COLORS } from "./shared";

function clock(ms: number | null): string {
  if (ms == null) return "--:--:--";
  return new Date(ms).toLocaleTimeString(undefined, { hour12: false });
}

function dur(ms: number | null): string {
  if (ms == null) return "open";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

function Pill({ state }: { state: string | null }) {
  if (!state) return <span className="text-muted-foreground">—</span>;
  return (
    <span
      className="rounded px-1.5 py-0.5 text-[11px] font-medium text-white"
      style={{ background: AFFECT_COLORS[state] ?? "#64748b" }}
    >
      {state}
    </span>
  );
}

/** The cycle behind a transition, so a row can be opened without leaving the timeline. */
function CycleDetail({ cycle }: { cycle: SessionCycle | undefined }) {
  if (!cycle) {
    return (
      <p className="px-3 py-2 text-[11px] italic text-muted-foreground">
        The cycle behind this transition is not in the loaded history.
      </p>
    );
  }
  const f = cycle.facial as Record<string, unknown> | null;
  const b = cycle.behavioural as Record<string, unknown> | null;
  const gateReason = cycle.gate?.reason ?? null;

  return (
    <div className="space-y-2 border-t border-border bg-muted/30 px-3 py-2 text-[11px]">
      <div className="grid gap-2 sm:grid-cols-3">
        <div>
          <p className="text-muted-foreground">Facial</p>
          <p className="font-mono">
            {f ? `${f.affect_state ?? "—"} · P(dis) ${(f.p_disengaged as number)?.toFixed(3) ?? "—"}` : "not recorded"}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">Behavioural</p>
          <p className="font-mono">
            {b ? `${b.affect_state ?? (b.empty_cycle ? "idle" : "—")} · P(conf) ${(b.p_confused as number)?.toFixed(3) ?? "—"}` : "not recorded"}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">Gate</p>
          <p className="font-mono">
            {gateReason ?? "not recorded"}
            {cycle.gate?.affect_source ? (
              <span className="text-muted-foreground"> · {cycle.gate.affect_source}</span>
            ) : null}
          </p>
        </div>
      </div>
      {cycle.strategy || cycle.triggered || cycle.delivered ? (
        <p className="font-mono text-emerald-700 dark:text-emerald-400">
          intervention · {String((cycle.strategy as Record<string, unknown>)?.action_type ?? "?")}
          {cycle.delivered ? " · delivered" : cycle.triggered ? " · generated, delivery unconfirmed" : ""}
        </p>
      ) : null}
    </div>
  );
}

export function DetectionTimeline({
  changes,
  cycles,
  loading,
}: {
  changes: StateChange[];
  cycles: SessionCycle[];
  loading?: boolean;
}) {
  const [open, setOpen] = useState<number | null>(null);

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading session history…</p>;
  }
  if (changes.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No state changes recorded for this session yet. A transition appears when the detected
        state differs from the previous cycle&apos;s.
      </p>
    );
  }

  const byCycle = new Map(cycles.map((c) => [c.cycle_number, c]));

  return (
    <div className="overflow-hidden rounded-md border border-border">
      <table className="w-full text-left text-xs">
        <thead className="bg-muted/50 text-[10px] uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">Time</th>
            <th className="px-3 py-2 font-medium">From</th>
            <th className="px-3 py-2 font-medium">To</th>
            <th className="px-3 py-2 text-right font-medium">Confidence</th>
            <th className="px-3 py-2 text-right font-medium">Held</th>
            <th className="px-3 py-2 text-right font-medium">Cycles</th>
            <th className="px-3 py-2 font-medium">Channel</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((c, i) => {
            const isOpen = open === i;
            return (
              <>
                <tr
                  key={`row-${i}`}
                  onClick={() => setOpen(isOpen ? null : i)}
                  className="cursor-pointer border-t border-border hover:bg-muted/40"
                >
                  <td className="px-3 py-1.5 font-mono tabular-nums">{clock(c.at)}</td>
                  <td className="px-3 py-1.5">
                    {c.from ? (
                      <Pill state={c.from} />
                    ) : (
                      <span
                        className="text-[10px] italic text-muted-foreground"
                        title="No observed predecessor: this run starts the session or follows a gap in observation."
                      >
                        —
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-1.5">
                    <Pill state={c.to} />
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                    {c.confidence != null ? `${Math.round(c.confidence * 100)}%` : "—"}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                    {dur(c.durationMs)}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums">{c.cycles}</td>
                  <td className="px-3 py-1.5 font-mono text-[10px] text-muted-foreground">
                    {c.source ?? "—"}
                  </td>
                </tr>
                {isOpen ? (
                  <tr key={`detail-${i}`}>
                    <td colSpan={7} className="p-0">
                      <CycleDetail cycle={c.cycle_number != null ? byCycle.get(c.cycle_number) : undefined} />
                    </td>
                  </tr>
                ) : null}
              </>
            );
          })}
        </tbody>
      </table>
      <p className="border-t border-border px-3 py-1.5 text-[10px] text-muted-foreground">
        Durations are derived from consecutive cycles — the system records a state per cycle, never
        a duration. A dash under &quot;From&quot; means no observed predecessor: the run starts the
        session or follows a gap in which nothing was detected. &quot;open&quot; means the run had
        not ended when this history was read.
      </p>
    </div>
  );
}
