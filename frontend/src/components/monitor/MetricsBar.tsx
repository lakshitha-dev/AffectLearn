"use client";

import { cn } from "@/lib/cn";
import type { MonitorHealth, MonitorMetrics } from "@/types/monitor";
import { fmtMs } from "./shared";

function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-lg font-semibold text-foreground">{value}</p>
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Dot({ ok, tone }: { ok?: boolean; tone?: "good" | "warn" | "bad" | "off" }) {
  const t = tone ?? (ok ? "good" : "bad");
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 rounded-full",
        t === "good" && "bg-green-500",
        t === "warn" && "bg-amber-500",
        t === "bad" && "bg-red-500",
        t === "off" && "bg-muted-foreground/40",
      )}
    />
  );
}

/** "4m ago" / "just now" -- so a stale panel says WHEN, not just that it is stale. */
function ago(ms: number | null): string | undefined {
  if (ms == null) return undefined;
  if (ms < 10_000) return "just now";
  const s = Math.round(ms / 1000);
  if (s < 90) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.round(m / 60)}h ago`;
}

const SESSION_LABEL: Record<MonitorMetrics["sessionState"], { text: string; tone: "good" | "warn" | "bad" | "off" }> = {
  active: { text: "active", tone: "good" },
  stale: { text: "stale", tone: "warn" },
  ended: { text: "ended", tone: "bad" },
  idle: { text: "none", tone: "off" },
};

export function MetricsBar({
  metrics,
  health,
  connected,
}: {
  metrics: MonitorMetrics;
  health?: MonitorHealth;
  connected: boolean;
}) {
  // A learner is actually being observed right now. Anything else means the values below are
  // the last ones seen, not the current ones.
  const live = metrics.sessionState === "active";

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
      <Stat label="Events/sec" value={metrics.eventsPerSec} hint={`${metrics.total} buffered`} />
      <Stat label="Cycles" value={metrics.cyclesObserved} />
      <Stat label="Avg node" value={fmtMs(metrics.avgNodeMs)} />
      <Stat
        label="Domain / Trace"
        value={`${metrics.domainCount} / ${metrics.traceCount}`}
      />
      {/* Transport only: whether THIS page is receiving the stream. Says nothing about
          whether a learner is present -- conflating the two is what made a closed camera and
          an ended session render as "live" with a face at 100%. */}
      <Stat
        label="Monitor"
        value={
          <span className="flex items-center gap-1.5 text-base">
            <Dot ok={connected} /> {connected ? "connected" : "offline"}
          </span>
        }
      />
      <Stat
        label="Session"
        value={
          <span className="flex items-center gap-1.5 text-base">
            <Dot tone={SESSION_LABEL[metrics.sessionState].tone} />
            {SESSION_LABEL[metrics.sessionState].text}
          </span>
        }
        hint={
          metrics.sessionState === "active" || metrics.sessionState === "idle"
            ? undefined
            : `last cycle ${ago(metrics.lastCycleAgeMs) ?? "unknown"}`
        }
      />
      {/* Per-cycle learner state, deliberately a Stat rather than a row in "Components" below --
          that list is server component health, and whether a face is in frame is not that. */}
      <Stat
        label="Face"
        value={
          metrics.facePresent == null || !live ? (
            <span className="text-base text-muted-foreground">—</span>
          ) : (
            <span className="flex items-center gap-1.5 text-base">
              <Dot ok={metrics.facePresent} />
              {metrics.facePresent ? "present" : "absent"}
            </span>
          )
        }
        // Presence is a property of a live camera. Once the session has ended or gone quiet
        // the last verdict is history, so it is reported as such instead of as the current
        // state -- this stat read "present, 100% of frames" for a session that had ended.
        hint={
          !live
            ? metrics.faceRatio == null
              ? "no active session"
              : `was ${Math.round(metrics.faceRatio * 100)}%, ${ago(metrics.lastCycleAgeMs) ?? "earlier"}`
            : metrics.faceRatio == null
              ? "no facial cycle yet"
              : `${Math.round(metrics.faceRatio * 100)}% of frames`
        }
      />
      <div className="rounded-lg border border-border bg-surface px-3 py-2">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Components</p>
        <div className="mt-1 space-y-0.5 text-[11px] text-muted-foreground">
          <p className="flex items-center gap-1.5">
            <Dot ok={!!health?.models.behavioral.available} /> behavioral model
          </p>
          <p className="flex items-center gap-1.5">
            <Dot ok={!!health?.models.facial.available} /> facial model
          </p>
          <p className="flex items-center gap-1.5">
            <Dot ok={!!health?.database.ok} /> database
          </p>
          <p className="flex items-center gap-1.5">
            <Dot ok={!!health?.redis.enabled} /> redis {health && !health.redis.enabled ? "(off)" : ""}
          </p>
        </div>
      </div>
    </div>
  );
}
