"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MonitorEvent } from "@/types/monitor";
import { NODE_STATUS_COLORS } from "./shared";

/** Durations of each node in the most-recent fully-observed cycle (a mini Gantt). */
export function CycleTimeline({ events }: { events: MonitorEvent[] }) {
  const { cycle, rows } = useMemo(() => {
    const completed = events.filter((e) => e.event_type === "node_completed");
    if (completed.length === 0) return { cycle: null as number | null, rows: [] };
    const latestCycle = completed.reduce(
      (m, e) => Math.max(m, (e.cycle_number as number) ?? -1),
      -1,
    );
    const rows = completed
      .filter((e) => e.cycle_number === latestCycle)
      .map((e) => ({
        node: e.node as string,
        ms: (e.duration_ms as number) ?? 0,
        stub: e.node_kind === "stub",
      }));
    return { cycle: latestCycle, rows };
  }, [events]);

  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">No completed node spans yet.</p>;
  }

  return (
    <div>
      <p className="mb-2 text-xs text-muted-foreground">
        Latest cycle {cycle != null ? `#${cycle}` : ""} — per-node execution time
      </p>
      <div style={{ height: rows.length * 34 + 24 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 10 }}>
            <XAxis type="number" tick={{ fontSize: 10 }} unit="ms" />
            <YAxis type="category" dataKey="node" width={110} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => [`${v} ms`, "duration"]} />
            <Bar dataKey="ms" radius={[0, 4, 4, 0]} isAnimationActive={false}>
              {rows.map((r, i) => (
                <Cell key={i} fill={r.stub ? NODE_STATUS_COLORS.idle : NODE_STATUS_COLORS.done} />
              ))}
              <LabelList
                dataKey="ms"
                position="right"
                formatter={(v: unknown) => `${v}ms`}
                style={{ fontSize: 10 }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
