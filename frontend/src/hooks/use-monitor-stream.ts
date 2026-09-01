"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useSessionStore } from "@/stores/session-store";
import type {
  AffectPoint,
  FacePresencePoint,
  MonitorEvent,
  MonitorMetrics,
  NodeRuntimeState,
  RouteDecision,
} from "@/types/monitor";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const MAX_EVENTS = 500;
/**
 * A learner cycle arrives roughly every 30s, so nothing for 75s means the session has gone
 * quiet rather than merely being between cycles. Deliberately not tied to the cycle interval
 * constant: this is a display tolerance, and making it 2.5x leaves room for the latency tail
 * (affect_detection has been observed above 5s) without flapping.
 */
const STALE_AFTER_MS = 75_000;

export type StreamStatus = "idle" | "connecting" | "open" | "error";

const AFFECT_EVENT_TYPES = new Set([
  "facial_affect_detected",
  "behavioral_affect_detected",
  "multimodal_affect_detected",
]);

interface DerivedState {
  nodeStates: Record<string, NodeRuntimeState>;
  lastRoute: RouteDecision | null;
  affectSeries: AffectPoint[];
  /**
   * Per-cycle face presence.
   *
   * `facial` below is last-write-wins, which cannot answer "when did they walk away". This series
   * is built the same way `affectSeries` is, from the bounded SSE buffer -- so it is only as deep
   * as the current connection (the buffer is cleared on a session-filter change).
   */
  facePresenceSeries: FacePresencePoint[];
  behavioral: Record<string, unknown> | null;
  facial: Record<string, unknown> | null;
  fusion: Record<string, unknown> | null;
  metrics: MonitorMetrics;
}

function derive(events: MonitorEvent[], now: number): DerivedState {
  const nodeStates: Record<string, NodeRuntimeState> = {};
  let lastRoute: RouteDecision | null = null;
  const affectSeries: AffectPoint[] = [];
  const facePresenceSeries: FacePresencePoint[] = [];
  let behavioral: Record<string, unknown> | null = null;
  let facial: Record<string, unknown> | null = null;
  let fusion: Record<string, unknown> | null = null;

  let domainCount = 0;
  let traceCount = 0;
  const cycles = new Set<number>();
  let nodeMsSum = 0;
  let nodeMsCount = 0;
  // `now` is the caller's clock (a 5s tick), not Date.now() read here: the events/sec window
  // and the staleness verdict must agree, and a tick-driven value is what makes staleness
  // advance when no events are arriving.
  let recentCount = 0;

  for (const e of events) {
    if (e.category === "domain") domainCount++;
    else if (e.category === "trace") traceCount++;
    if (typeof e.cycle_number === "number") cycles.add(e.cycle_number);
    if (typeof e.timestamp === "number" && now - e.timestamp <= 10_000) recentCount++;

    const node = e.node as string | undefined;
    switch (e.event_type) {
      case "node_started":
        if (node)
          nodeStates[node] = {
            status: "running",
            kind: e.node_kind as NodeRuntimeState["kind"],
            lastCycle: (e.cycle_number as number) ?? null,
          };
        break;
      case "node_completed":
        if (node) {
          const ms = e.duration_ms as number | undefined;
          nodeStates[node] = {
            status: "done",
            kind: e.node_kind as NodeRuntimeState["kind"],
            lastDurationMs: ms,
            lastCycle: (e.cycle_number as number) ?? null,
          };
          if (typeof ms === "number") {
            nodeMsSum += ms;
            nodeMsCount++;
          }
        }
        break;
      case "node_error":
        if (node)
          nodeStates[node] = {
            status: "error",
            kind: e.node_kind as NodeRuntimeState["kind"],
            lastCycle: (e.cycle_number as number) ?? null,
          };
        break;
      case "route_decision":
        lastRoute = {
          chosen: e.chosen as string,
          phase: e.phase as string | undefined,
          group: e.group as string | undefined,
          reason: e.reason as string | undefined,
          cycle: (e.cycle_number as number) ?? null,
          t: e.timestamp as number,
        };
        break;
    }

    if (AFFECT_EVENT_TYPES.has(e.event_type)) {
      const p = (e.payload as Record<string, unknown>) ?? {};
      const affect = (p.affect_state as string) ?? "";
      const confidence = (p.affect_confidence as number) ?? 0;
      if (affect) {
        affectSeries.push({
          t: e.timestamp as number,
          cycle: (e.cycle_number as number) ?? null,
          affect,
          confidence,
          source: p.affect_source as string,
          mode: p.detection_mode as string,
        });
      }
      if (e.event_type === "behavioral_affect_detected") behavioral = p;
      if (e.event_type === "facial_affect_detected") {
        facial = p;
        // Only record presence when the payload actually reports it. A legacy event has no
        // frames_with_face, and inventing a zero would read as "nobody was there".
        const seen = p.frames_with_face;
        if (typeof seen === "number") {
          const captured = (p.frames_captured as number) ?? 0;
          facePresenceSeries.push({
            t: e.timestamp as number,
            cycle: (e.cycle_number as number) ?? null,
            seen,
            captured,
            ratio: typeof p.face_ratio === "number" ? p.face_ratio : 0,
            absent: Boolean(p.face_absent),
          });
        }
      }
      if (e.event_type === "multimodal_affect_detected") fusion = p;
    }
  }

  // Session liveness. Read from the events themselves rather than from the admin SSE
  // connection: the page being open says nothing about whether a learner is present.
  let lastCycleAt: number | null = null;
  let lastDisconnectAt: number | null = null;
  for (const e of events) {
    const ts = typeof e.timestamp === "number" ? e.timestamp : null;
    if (ts == null) continue;
    if (e.event_type === "ws_disconnected") {
      if (lastDisconnectAt == null || ts > lastDisconnectAt) lastDisconnectAt = ts;
    } else if (e.cycle_number != null && e.cycle_number > 0) {
      if (lastCycleAt == null || ts > lastCycleAt) lastCycleAt = ts;
    }
  }

  let sessionState: MonitorMetrics["sessionState"];
  if (lastCycleAt == null) {
    sessionState = "idle";
  } else if (lastDisconnectAt != null && lastDisconnectAt >= lastCycleAt) {
    // An explicit end beats a timeout: report it immediately rather than waiting to go stale.
    sessionState = "ended";
  } else if (now - lastCycleAt > STALE_AFTER_MS) {
    sessionState = "stale";
  } else {
    sessionState = "active";
  }

  const metrics: MonitorMetrics = {
    total: events.length,
    domainCount,
    traceCount,
    eventsPerSec: Math.round((recentCount / 10) * 100) / 100,
    cyclesObserved: cycles.size,
    avgNodeMs: nodeMsCount ? Math.round((nodeMsSum / nodeMsCount) * 100) / 100 : null,
    faceRatio: facePresenceSeries.length
      ? facePresenceSeries[facePresenceSeries.length - 1].ratio
      : null,
    facePresent: facePresenceSeries.length
      ? !facePresenceSeries[facePresenceSeries.length - 1].absent
      : null,
    sessionState,
    lastCycleAt,
    lastCycleAgeMs: lastCycleAt == null ? null : Math.max(0, now - lastCycleAt),
  };

  return {
    nodeStates,
    lastRoute,
    affectSeries: affectSeries.slice(-60),
    facePresenceSeries: facePresenceSeries.slice(-60),
    behavioral,
    facial,
    fusion,
    metrics,
  };
}

/**
 * Subscribes to the backend Monitor SSE stream for live observability events.
 * Re-connects when the session filter or access token changes; EventSource itself
 * retries transient network drops. Keeps a bounded event list + derived view state.
 */
export function useMonitorStream(sessionId: string | null) {
  const accessToken = useSessionStore((s) => s.accessToken);
  const [events, setEvents] = useState<MonitorEvent[]>([]);
  const [status, setStatus] = useState<StreamStatus>("idle");
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!accessToken) {
      setStatus("idle");
      return;
    }
    setEvents([]);
    setStatus("connecting");

    const params = new URLSearchParams({ token: accessToken });
    if (sessionId) params.set("session_id", sessionId);
    const es = new EventSource(`${API_BASE}/monitor/stream?${params.toString()}`);
    esRef.current = es;

    es.onopen = () => setStatus("open");
    es.onmessage = (ev) => {
      try {
        const parsed = JSON.parse(ev.data) as MonitorEvent;
        setEvents((prev) => {
          const next = prev.length >= MAX_EVENTS ? prev.slice(prev.length - MAX_EVENTS + 1) : prev.slice();
          next.push(parsed);
          return next;
        });
      } catch {
        /* keep-alive comment frames are not JSON — ignore */
      }
    };
    es.onerror = () => setStatus("error"); // EventSource auto-reconnects

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [accessToken, sessionId]);

  // Staleness has to advance on the clock, not on event arrival -- a session going quiet
  // produces no event to re-render on, which is exactly the case that was rendering as live.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(id);
  }, []);

  const derived = useMemo(() => derive(events, now), [events, now]);
  return { status, events, ...derived };
}
