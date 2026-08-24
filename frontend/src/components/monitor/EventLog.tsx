"use client";

import { useMemo, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/cn";
import type { MonitorEvent } from "@/types/monitor";
import { fmtTime } from "./shared";

type Filter = "all" | "domain" | "trace";

const EVENT_COLORS: Record<string, string> = {
  node_started: "text-blue-500",
  node_completed: "text-green-600",
  node_error: "text-red-500",
  route_decision: "text-violet-500",
};

function summary(e: MonitorEvent): string {
  if (e.node) {
    const dur = e.duration_ms != null ? ` ${e.duration_ms}ms` : "";
    // A node_error's message was colour-coded but never shown, so a failing cycle looked
    // identical to a fast one.
    const err = e.event_type === "node_error" && e.error ? ` — ${String(e.error)}` : "";
    return `${e.node}${dur}${err}`;
  }
  if (e.event_type === "route_decision") {
    const why = e.reason ? ` (${String(e.reason)})` : "";
    return `→ ${e.chosen}${why}`;
  }

  const p = (e.payload as Record<string, unknown>) ?? {};

  // The gate decision, which appears nowhere else in the live UI — only aggregated.
  if (typeof p.adaptation_gate === "string") {
    const state = p.affect_state ? `${p.affect_state} · ` : "";
    return `${state}gate: ${p.adaptation_gate}`;
  }

  if (p.affect_state) {
    // Guard on the field being FORMATTED, not a sibling. Guarding on affect_state while
    // formatting affect_confidence rendered "engaged (NaN%)" for every learner_profile_updated
    // event, which carries a state but has never carried a confidence.
    const c = p.affect_confidence ?? p.confidence;
    if (typeof c === "number" && Number.isFinite(c)) {
      return `${p.affect_state} (${Math.round(c * 100)}%)`;
    }
    return String(p.affect_state);
  }
  return "";
}

export function EventLog({ events }: { events: MonitorEvent[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [expanded, setExpanded] = useState<number | null>(null);

  const rows = useMemo(() => {
    const filtered = filter === "all" ? events : events.filter((e) => e.category === filter);
    return filtered.slice(-200).reverse();
  }, [events, filter]);

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex gap-1">
        {(["all", "domain", "trace"] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "rounded px-2 py-0.5 text-xs capitalize transition-colors",
              filter === f ? "bg-primary text-primary-foreground" : "bg-border/40 text-muted-foreground hover:bg-border",
            )}
          >
            {f}
          </button>
        ))}
      </div>
      <ScrollArea className="h-[340px] rounded-md border border-border">
        <div className="divide-y divide-border/60 font-mono text-[11px]">
          {rows.length === 0 && (
            <p className="p-3 text-muted-foreground">waiting for events…</p>
          )}
          {rows.map((e, i) => {
            const idx = events.length - 1 - i;
            const isOpen = expanded === idx;
            return (
              <div key={`${e.timestamp}-${idx}`}>
                <button
                  onClick={() => setExpanded(isOpen ? null : idx)}
                  className="flex w-full items-center gap-2 px-2 py-1 text-left hover:bg-border/30"
                >
                  <span className="shrink-0 text-muted-foreground">{fmtTime(e.timestamp)}</span>
                  <span
                    className={cn(
                      "shrink-0 rounded px-1 text-[10px]",
                      e.category === "trace" ? "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300" : "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
                    )}
                  >
                    {e.category}
                  </span>
                  <span className={cn("shrink-0 font-medium", EVENT_COLORS[e.event_type] ?? "text-foreground")}>
                    {e.event_type}
                  </span>
                  <span className="truncate text-muted-foreground">{summary(e)}</span>
                  {e.cycle_number != null && (
                    <span className="ml-auto shrink-0 text-muted-foreground">#{e.cycle_number}</span>
                  )}
                </button>
                {isOpen && (
                  <pre className="overflow-x-auto bg-background px-3 py-2 text-[10px] text-muted-foreground">
                    {JSON.stringify(e, null, 2)}
                  </pre>
                )}
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
