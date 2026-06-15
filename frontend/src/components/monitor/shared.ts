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
