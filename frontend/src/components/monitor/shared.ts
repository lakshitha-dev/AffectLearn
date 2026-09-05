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
 * `bored` was added when the geometric facial channel shipped. It is the state that channel
 * exists to detect (EngageNet low-engagement, AUC 0.9225), and leaving it out of this list had a
 * visible consequence: `AffectStream` maps each point to a lane by name, so every `bored`
 * detection resolved to `lane: undefined` and Recharts drew nothing. The stream sat empty while
 * the aggregate tab counted the cycles — the two views disagreeing because one of them filtered
 * out the only state being produced.
 *
 * `frustrated` stays out, and that is a measurement rather than an oversight: no deployed model
 * emits it (both facial artifacts and the behavioural GBDT pin it at 0.0), so a lane for it would
 * read as "this learner was never frustrated" instead of "frustration is not detectable here".
 *
 * AFFECT_COLORS deliberately keeps all four: the designer heatmap still uses the full palette.
 */
export const DETECTABLE_AFFECTS = ["bored", "confused", "engaged"] as const;

/**
 * Detectability is a property of the CHANNEL, not of the system.
 *
 * The behavioural GBDT emits P(confused) and pins bored and frustrated at 0.0, so a `bored` bar
 * on that panel would be permanently empty and would read as "this learner was never bored"
 * rather than "this channel cannot see boredom". The geometric facial channel is the mirror
 * image: `bored` is the state it exists to detect, and `confused` is invisible to it.
 *
 * The union above is what the affect STREAM needs — it plots whatever any channel produced, and
 * omitting a state there drops the point entirely rather than drawing an empty bar.
 */
export const BEHAVIORAL_DETECTABLE = ["confused", "engaged"] as const;

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

/**
 * "4m ago" / "just now" — so a stale panel says WHEN, not merely that it is stale.
 *
 * Lifted out of MetricsBar when staleness was wired into the per-channel panels: the SESSION card
 * was the only place that degraded when a session ended, while Facial Analysis and the face
 * presence strip kept rendering the last cycle in the present tense indefinitely. An ended session
 * then looked identical to a live one, which is how a monitor came to show 100% face presence for
 * a learner who had no camera open.
 */
export function ago(ms: number | null | undefined): string | undefined {
  if (ms == null) return undefined;
  if (ms < 10_000) return "just now";
  const s = Math.round(ms / 1000);
  if (s < 90) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.round(m / 60)}h ago`;
}
