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

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      className={cn("inline-block h-2 w-2 rounded-full", ok ? "bg-green-500" : "bg-red-500")}
    />
  );
}

export function MetricsBar({
  metrics,
  health,
  connected,
}: {
  metrics: MonitorMetrics;
  health?: MonitorHealth;
  connected: boolean;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <Stat label="Events/sec" value={metrics.eventsPerSec} hint={`${metrics.total} buffered`} />
      <Stat label="Cycles" value={metrics.cyclesObserved} />
      <Stat label="Avg node" value={fmtMs(metrics.avgNodeMs)} />
      <Stat
        label="Domain / Trace"
        value={`${metrics.domainCount} / ${metrics.traceCount}`}
      />
      <Stat
        label="Stream"
        value={
          <span className="flex items-center gap-1.5 text-base">
            <Dot ok={connected} /> {connected ? "live" : "offline"}
          </span>
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
