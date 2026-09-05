"use client";

/**
 * Query hooks for the admin monitor endpoints.
 *
 * The admin pages previously called `apiFetch` inline inside `useQuery` — the one place in the
 * app that bypassed the per-domain hook layer. This mirrors `use-analytics.ts` so query keys
 * and stale times live in one place and pages stay declarative.
 */

import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiFetchBlob, saveBlob } from "@/lib/api-client";
import type {
  SessionHistory,
  GraphTopology,
  MonitorAggregates,
  MonitorHealth,
  MonitorSessions,
} from "@/types/monitor";

export const MONITOR_KEY = "monitor";

/** Component + model + vLLM health. Polled: this is the liveness surface. */
export function useMonitorHealth(pollMs = 5000) {
  return useQuery<MonitorHealth>({
    queryKey: [MONITOR_KEY, "health"],
    queryFn: () => apiFetch<MonitorHealth>("/monitor/health"),
    refetchInterval: pollMs,
    staleTime: 0,
  });
}

/** Static agent-graph topology — never changes at runtime, so fetch once. */
export function useMonitorGraph() {
  return useQuery<GraphTopology>({
    queryKey: [MONITOR_KEY, "graph"],
    queryFn: () => apiFetch<GraphTopology>("/monitor/graph"),
    staleTime: Infinity,
  });
}

/** Active WS sessions plus session ids seen in the recent event buffer. */
export function useMonitorSessions(pollMs = 5000) {
  return useQuery<MonitorSessions>({
    queryKey: [MONITOR_KEY, "sessions"],
    queryFn: () => apiFetch<MonitorSessions>("/monitor/sessions"),
    refetchInterval: pollMs,
    staleTime: 0,
  });
}

/**
 * Windowed aggregates. Polled slowly — this scans research_events, and the numbers move on
 * the scale of minutes, not seconds.
 */
export function useMonitorAggregates(hours: number) {
  return useQuery<MonitorAggregates>({
    queryKey: [MONITOR_KEY, "aggregates", hours],
    queryFn: () => apiFetch<MonitorAggregates>(`/monitor/aggregates?hours=${hours}`),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

/**
 * One session reconstructed from the research record, indexed by cycle.
 *
 * Separate from `useMonitorStream` on purpose. The stream answers "what is happening now" from a
 * 500-slot in-process ring; this answers "what happened during this session" from the database,
 * and survives a page reload or a backend restart, which the stream does not.
 *
 * Polled while a session is live so the timeline keeps growing, but slowly: it reads
 * `research_events` and a cycle only lands every ~30 s.
 */
export function useSessionHistory(sessionId: string | null) {
  return useQuery<SessionHistory>({
    queryKey: [MONITOR_KEY, "session", sessionId],
    queryFn: () => apiFetch<SessionHistory>(`/monitor/session/${sessionId}`),
    enabled: Boolean(sessionId),
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}

/**
 * Download the window's events as CSV.
 *
 * Not a `useQuery` — a download is an imperative user action with no cached result, and caching a
 * multi-megabyte Blob in the query client would be actively harmful.
 */
export async function exportMonitorCsv(hours: number, sessionId?: string | null): Promise<void> {
  const params = new URLSearchParams({ hours: String(hours) });
  if (sessionId) params.set("session_id", sessionId);
  const blob = await apiFetchBlob(`/monitor/export.csv?${params.toString()}`);
  // The server sets its own filename on Content-Disposition, but fetch cannot read it here
  // without exposing the header via CORS, so mirror its naming client-side.
  const stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";
  saveBlob(blob, `affectlearn-events-${stamp}-${hours}h.csv`);
}
