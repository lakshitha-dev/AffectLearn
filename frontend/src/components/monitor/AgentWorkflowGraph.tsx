"use client";

import "@xyflow/react/dist/style.css";

import { useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge,
} from "@xyflow/react";
import { Sparkles } from "lucide-react";

import { cn } from "@/lib/cn";
import {
  ServiceNodeView,
  StepNodeView,
  type ServiceNode,
  type StepNode,
} from "@/components/monitor/WorkflowNode";
import { buildWorkflow, type BuildInput } from "@/components/monitor/workflow-model";
import { fmtMs } from "@/components/monitor/shared";

const NODE_TYPES = { step: StepNodeView, service: ServiceNodeView };

/**
 * The agent graph as a live workflow canvas: every node of `app/agents/graph.py` as a typed card,
 * connectors from the graph's own edges, the route the last cycle took lit and animated, and the
 * external service each agent depends on as a badge beside it.
 */
export function AgentWorkflowGraph(props: BuildInput & { live?: boolean }) {
  const { live, ...input } = props;
  const model = useMemo(
    () => buildWorkflow(input),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [input.topology, input.nodeStates, input.lastRoute, input.cycle, input.health],
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const nodes = useMemo<(StepNode | ServiceNode)[]>(
    () => [
      ...model.steps.map<StepNode>((s) => ({
        id: s.id,
        type: "step",
        position: s.position,
        data: s,
        draggable: false,
        selected: s.id === selectedId,
      })),
      ...model.services.map<ServiceNode>((s) => ({
        id: s.id,
        type: "service",
        position: s.position,
        data: s,
        draggable: false,
        selectable: false,
        focusable: false,
      })),
    ],
    [model, selectedId],
  );

  const edges = useMemo<Edge[]>(
    () =>
      model.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        type: "default", // bezier: the curved connectors of a workflow builder
        label: e.label,
        animated: e.taken && live,
        markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
        style: {
          stroke: e.taken ? "rgb(var(--primary))" : "rgb(var(--muted) / 0.5)",
          strokeWidth: e.taken ? 2.25 : 1.5,
          opacity: model.route && !e.taken ? 0.45 : 1,
        },
        labelStyle: { fontSize: 11, fontWeight: 600, fill: "rgb(var(--muted-foreground))" },
        labelBgStyle: { fill: "rgb(var(--card))" },
        labelBgPadding: [6, 3] as [number, number],
        labelBgBorderRadius: 6,
      })),
    [model, live],
  );

  const selected = model.steps.find((s) => s.id === selectedId) ?? null;

  return (
    <div className="space-y-3">
      <div
        className={cn(
          "relative h-[960px] overflow-hidden rounded-2xl border border-border",
          "bg-gradient-to-b from-primary-soft/60 via-card to-card",
        )}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          fitView
          fitViewOptions={{ padding: 0.04 }}
          minZoom={0.4}
          maxZoom={1.6}
          nodesDraggable={false}
          nodesConnectable={false}
          zoomOnScroll={false}
          preventScrolling={false}
          onNodeClick={(_, n) => {
            if (n.type === "step") setSelectedId((cur) => (cur === n.id ? null : n.id));
          }}
          onPaneClick={() => setSelectedId(null)}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} color="rgb(var(--muted) / 0.25)" />
          <Controls showInteractive={false} position="bottom-right" />
        </ReactFlow>

        {!model.hasActivity && (
          <div className="pointer-events-none absolute inset-x-0 top-4 flex justify-center">
            <p className="flex items-center gap-2 rounded-full border border-border bg-card/90 px-4 py-1.5 text-sm text-muted-foreground shadow-sm">
              <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
              Waiting for a learner cycle — open a lesson as a learner to watch the agents work.
            </p>
          </div>
        )}
      </div>

      <Legend route={model.route} />

      {selected && (
        <div className="rounded-xl border border-border bg-surface/70 p-4" aria-live="polite">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {selected.eyebrow}
          </p>
          <p className="text-sm font-semibold text-foreground">{selected.title}</p>
          <p className="mt-1 text-sm text-muted-foreground">{selected.detail}</p>
          {selected.desc && <p className="mt-2 text-xs text-muted-foreground">{selected.desc}</p>}
          <p className="mt-2 text-xs text-muted-foreground">
            Status: {selected.status}
            {selected.durationMs != null ? ` · last run ${fmtMs(selected.durationMs)}` : ""}
          </p>
        </div>
      )}
    </div>
  );
}

function Legend({ route }: { route: "adaptive" | "log_only" | null }) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
      <span className="flex items-center gap-1.5">
        <span className="h-0.5 w-6 rounded bg-primary" /> route taken
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-0.5 w-6 rounded bg-muted/50" /> not taken
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-success" /> step done
      </span>
      <span className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full bg-primary" /> running
      </span>
      <span className="ml-auto font-medium text-foreground">
        {route === "adaptive"
          ? "Last cycle: gate passed → agents adapted the lesson"
          : route === "log_only"
            ? "Last cycle: held back → recorded only"
            : "No cycle yet"}
      </span>
    </div>
  );
}
