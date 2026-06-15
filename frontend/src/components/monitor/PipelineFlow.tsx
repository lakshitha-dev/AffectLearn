"use client";

import { cn } from "@/lib/cn";
import type { GraphNode, GraphTopology, NodeRuntimeState, RouteDecision } from "@/types/monitor";
import { fmtMs, NODE_STATUS_COLORS } from "./shared";

interface PipelineFlowProps {
  topology: GraphTopology | undefined;
  nodeStates: Record<string, NodeRuntimeState>;
  lastRoute: RouteDecision | null;
  facialAvailable?: boolean;
}

function NodeCard({
  node,
  state,
  note,
}: {
  node: GraphNode;
  state?: NodeRuntimeState;
  note?: string;
}) {
  const status = state?.status ?? "idle";
  const color = NODE_STATUS_COLORS[status];
  const isStub = node.kind === "stub";
  return (
    <div
      className={cn(
        "relative w-44 rounded-lg border bg-surface px-3 py-2 transition-all",
        status === "running" && "animate-pulse",
        isStub && "opacity-60 border-dashed",
      )}
      style={{ borderColor: color, boxShadow: status === "running" ? `0 0 0 2px ${color}33` : undefined }}
      title={node.desc}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-foreground">{node.label}</span>
        <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
      </div>
      <div className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span className="capitalize">{status}</span>
        {state?.lastDurationMs != null && <span>· {fmtMs(state.lastDurationMs)}</span>}
        {state?.lastCycle != null && <span>· #{state.lastCycle}</span>}
      </div>
      {isStub && (
        <span className="absolute -top-2 right-2 rounded-full bg-amber-100 px-1.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">
          stub
        </span>
      )}
      {note && <p className="mt-1 text-[10px] leading-tight text-red-500">{note}</p>}
    </div>
  );
}

function Arrow({ active, label }: { active?: boolean; label?: string }) {
  return (
    <div className="flex shrink-0 flex-col items-center justify-center px-1">
      {label && <span className="mb-0.5 text-[10px] text-muted-foreground">{label}</span>}
      <span className={cn("text-lg", active ? "text-primary" : "text-border")}>→</span>
    </div>
  );
}

export function PipelineFlow({ topology, nodeStates, lastRoute, facialAvailable }: PipelineFlowProps) {
  if (!topology) return <div className="text-sm text-muted-foreground">Loading topology…</div>;
  const byId = Object.fromEntries(topology.nodes.map((n) => [n.id, n]));
  const tookAdaptive = lastRoute?.chosen === "pedagogical";
  const tookLogOnly = lastRoute?.chosen === "log_only";
  const facialNote =
    facialAvailable === false ? "facial model unavailable — behavioral only" : undefined;

  return (
    <div className="space-y-4">
      {/* Main spine */}
      <div className="flex flex-wrap items-center gap-1">
        <div className="rounded-md bg-border/60 px-2 py-1 text-xs font-medium text-muted-foreground">START</div>
        <Arrow active />
        <NodeCard node={byId.affect_detection} state={nodeStates.affect_detection} note={facialNote} />
        <Arrow active />
        <NodeCard node={byId.learner_profiler} state={nodeStates.learner_profiler} />
        <Arrow active={tookLogOnly} label="if control" />
        <NodeCard node={byId.log_only} state={nodeStates.log_only} />
        <Arrow active={tookLogOnly} />
        <div className="rounded-md bg-border/60 px-2 py-1 text-xs font-medium text-muted-foreground">END</div>
      </div>

      {/* Adaptive branch */}
      <div className="flex flex-wrap items-center gap-1 pl-8">
        <Arrow active={tookAdaptive} label="if adaptive" />
        <NodeCard node={byId.pedagogical} state={nodeStates.pedagogical} />
        <Arrow active={tookAdaptive} />
        <NodeCard node={byId.content_adapter} state={nodeStates.content_adapter} />
        <Arrow active={tookAdaptive} />
        <NodeCard node={byId.deliver} state={nodeStates.deliver} />
        <Arrow active={tookAdaptive} />
        <div className="rounded-md bg-border/60 px-2 py-1 text-xs font-medium text-muted-foreground">END</div>
      </div>

      {/* Routing decision */}
      <div className="rounded-md border border-border bg-background px-3 py-2 text-xs">
        <span className="font-medium text-foreground">Last routing decision: </span>
        {lastRoute ? (
          <span className="text-muted-foreground">
            <span className="font-mono text-foreground">{lastRoute.chosen}</span>
            {lastRoute.reason ? ` — ${lastRoute.reason}` : ""}
            {lastRoute.cycle != null ? ` (cycle #${lastRoute.cycle})` : ""}
          </span>
        ) : (
          <span className="text-muted-foreground">no cycle observed yet</span>
        )}
      </div>
    </div>
  );
}
