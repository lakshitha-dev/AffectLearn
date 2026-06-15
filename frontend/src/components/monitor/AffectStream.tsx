"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AFFECT_LABELS, type AffectPoint } from "@/types/monitor";
import { affectColor, fmtTime } from "./shared";

// Map affect category → numeric lane so we can plot it as a step series.
const LANE: Record<string, number> = { bored: 0, confused: 1, engaged: 2, frustrated: 3 };

export function AffectStream({ series }: { series: AffectPoint[] }) {
  const latest = series[series.length - 1];
  const data = series.map((p) => ({
    t: p.t,
    lane: LANE[p.affect] ?? 0,
    affect: p.affect,
    confidence: p.confidence,
  }));

  return (
    <div>
      <div className="mb-3 flex items-center gap-3">
        {latest ? (
          <>
            <span
              className="rounded-full px-3 py-1 text-sm font-semibold text-white"
              style={{ background: affectColor(latest.affect) }}
            >
              {latest.affect}
            </span>
            <span className="text-sm text-muted-foreground">
              {(latest.confidence * 100).toFixed(0)}% · {latest.source ?? "—"} · {latest.mode ?? "—"}
            </span>
          </>
        ) : (
          <span className="text-sm text-muted-foreground">awaiting affect events…</span>
        )}
      </div>
      <div className="h-44 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 12, bottom: 5, left: -10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" opacity={0.1} />
            <XAxis dataKey="t" tickFormatter={fmtTime} tick={{ fontSize: 10 }} minTickGap={40} />
            <YAxis
              type="number"
              domain={[-0.5, 3.5]}
              ticks={[0, 1, 2, 3]}
              tickFormatter={(v: number) => AFFECT_LABELS[v] ?? ""}
              tick={{ fontSize: 10 }}
              width={70}
            />
            <Tooltip
              labelFormatter={(t) => fmtTime(t as number)}
              formatter={(_v, _n, p) => {
                const row = p.payload as { affect: string; confidence: number };
                return [`${row.affect} (${(row.confidence * 100).toFixed(0)}%)`, "affect"];
              }}
            />
            <Line
              type="stepAfter"
              dataKey="lane"
              stroke="#6366f1"
              strokeWidth={2}
              dot={{ r: 3 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
