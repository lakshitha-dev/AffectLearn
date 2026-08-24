// Shared palette + formatters for the observability dashboard panels.

import type { NodeRuntimeStatus } from "@/types/monitor";

// Affect category colors (match the designer analytics heatmap palette).
export const AFFECT_COLORS: Record<string, string> = {
  bored: "#94a3b8", // slate-400
  confused: "#f59e0b", // amber-500
  engaged: "#22c55e", // green-500
  frustrated: "#ef4444", // red-500
};

export function affectColor(a?: string): string {
  return (a && AFFECT_COLORS[a]) || "#64748b";
}

/**
 * The affect states the DEPLOYED models can actually produce.
 *
 * Both models are binary confusion detectors, so `bored` and `frustrated` can never be
 * emitted — they measured at chance in the available data and are pinned to 0.0 server-side.
 * The monitor renders only these two rather than four lanes, three of which would sit flat at
 * zero and read as "this learner was never bored" instead of "boredom is not detectable".
 *
 * AFFECT_COLORS deliberately keeps all four: the designer heatmap still uses the full palette.
 */
export const DETECTABLE_AFFECTS = ["confused", "engaged"] as const;

export const NODE_STATUS_COLORS: Record<NodeRuntimeStatus, string> = {
  idle: "#64748b", // slate-500
  running: "#3b82f6", // blue-500
  done: "#22c55e", // green-500
  error: "#ef4444", // red-500
};

export function fmtMs(ms?: number | null): string {
  if (ms == null) return "—";
  return ms < 10 ? `${ms.toFixed(2)}ms` : `${Math.round(ms)}ms`;
}

export function fmtTime(t?: number): string {
  if (!t) return "";
  return new Date(t).toLocaleTimeString(undefined, { hour12: false });
}

export function shortId(id?: string | null): string {
  if (!id) return "—";
  return id.length > 10 ? `${id.slice(0, 8)}…` : id;
}
