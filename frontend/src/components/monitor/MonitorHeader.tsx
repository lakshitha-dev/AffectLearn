"use client";

import { cn } from "@/lib/cn";
import { ago, shortId } from "@/components/monitor/shared";
import type { DecisionReport, MonitorMetrics } from "@/types/monitor";

/**
 * "Live · session 1a2b3c4d · last cycle 4s ago" -- the one line an operator reads first.
 * Calm grey when nothing is running, so an idle monitor reads as idle rather than broken.
 */
export function LiveStatusPill({
  sessionState,
  connected,
  sessionId,
  lastCycleAgeMs,
}: {
  sessionState: MonitorMetrics["sessionState"];
  connected: boolean;
  sessionId: string | null;
  lastCycleAgeMs: number | null | undefined;
}) {
  const live = connected && sessionState === "active";
  const label = !connected
    ? "Stream offline"
    : live
      ? "Live"
      : sessionState === "stale"
        ? "Quiet"
        : sessionState === "ended"
          ? "Session ended"
          : "Idle — no learner connected";
  const since = ago(lastCycleAgeMs);

  return (
    <span
      role="status"
      className={cn(
        "inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold",
        live
          ? "bg-success/10 text-success"
          : !connected
            ? "bg-error/10 text-error"
            : "bg-surface text-muted-foreground",
      )}
    >
      <span className="relative flex h-2 w-2" aria-hidden="true">
        {live && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success/60" />
        )}
        <span
          className={cn(
            "relative inline-flex h-2 w-2 rounded-full",
            live ? "bg-success" : !connected ? "bg-error" : "bg-muted",
          )}
        />
      </span>
      {label}
      {live && sessionId ? <span className="font-normal">· session {shortId(sessionId)}</span> : null}
      {live && since ? <span className="font-normal">· last cycle {since}</span> : null}
    </span>
  );
}

function Chip({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "warn" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs",
        tone === "warn"
          ? "border-warning/30 bg-warning/10 text-warning"
          : "border-border bg-surface text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}

const short = (k: string) => k.replace("_model", "").replace("facial_", "");

/**
 * What is actually loaded and how the gate is set, read from the live config. It replaces a
 * single run-on monospace line that listed the same facts.
 */
export function ConfigChips({
  behavioralKind,
  facialKind,
  decision,
}: {
  behavioralKind?: string;
  facialKind?: string;
  decision?: DecisionReport;
}) {
  if (!behavioralKind && !facialKind && !decision) return null;
  const floors = decision?.channelMinConfidence
    ? Object.entries(decision.channelMinConfidence)
    : [];
  return (
    <div className="flex flex-wrap gap-1.5" aria-label="Pipeline configuration">
      <Chip>facial: {facialKind ?? "—"}</Chip>
      <Chip>behavioural: {behavioralKind ?? "—"}</Chip>
      {decision?.adaptStates?.length ? <Chip>acts on: {decision.adaptStates.join(", ")}</Chip> : null}
      {floors.length ? (
        <Chip>gates: {floors.map(([k, v]) => `${short(k)} ${v}`).join(", ")}</Chip>
      ) : decision?.adaptMinConfidence != null ? (
        <Chip>gate: {decision.adaptMinConfidence}</Chip>
      ) : null}
      {decision?.decisiveAffectSources?.length ? (
        <Chip>decisive: {decision.decisiveAffectSources.map(short).join(", ")}</Chip>
      ) : null}
      {decision?.fusionDrivesDecision === false ? <Chip>channels routed, not fused</Chip> : null}
      {decision?.forcedMode && decision.forcedMode !== "auto" ? (
        <Chip tone="warn">mode forced: {decision.forcedMode}</Chip>
      ) : null}
    </div>
  );
}
