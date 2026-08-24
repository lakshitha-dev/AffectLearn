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
import { type AffectPoint } from "@/types/monitor";
import { DETECTABLE_AFFECTS, affectColor, fmtTime } from "./shared";

// Map affect category → numeric lane so we can plot it as a step series.
//
// Only the two states the deployed models can emit get a lane. The chart used to reserve four,
// so `bored` and `frustrated` drew as permanently-empty tracks — which reads as "this learner
// was never bored" rather than "boredom is not measurable with these models". They are pinned
// to 0.0 server-side, so a lane for them could never carry a point.
const LANES: readonly string[] = DETECTABLE_AFFECTS;
const LANE: Record<string, number> = LANES.reduce<Record<string, number>>((acc, a, i) => {
  acc[a] = i;
  return acc;
}, {});

export function AffectStream({ series }: { series: AffectPoint[] }) {
  const latest = series[series.length - 1];
  const data = series.map((p) => ({
    t: p.t,
    // An out-of-vocabulary state would otherwise silently render as lane 0 (`confused`).
    lane: LANE[p.affect],
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
              domain={[-0.5, LANES.length - 0.5]}
              ticks={LANES.map((_, i) => i)}
              tickFormatter={(v: number) => LANES[v] ?? ""}
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
              connectNulls={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
