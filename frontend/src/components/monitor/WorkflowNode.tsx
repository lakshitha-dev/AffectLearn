"use client";

import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import {
  Brain,
  CircleCheck,
  CircleAlert,
  CirclePlay,
  Database,
  FileText,
  Flag,
  GitBranch,
  Loader,
  PenLine,
  ScanFace,
  Send,
  Zap,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/cn";
import { fmtMs } from "@/components/monitor/shared";
import type { ServiceData, StepData, StepKind } from "@/components/monitor/workflow-model";
import { STEP_WIDTH } from "@/components/monitor/workflow-model";

/** Each kind gets its own icon and eyebrow tint, like the node types of a workflow builder. */
const KIND_STYLE: Record<StepKind, { icon: LucideIcon; tint: string; chip: string }> = {
  trigger: { icon: Zap, tint: "text-sky-600 dark:text-sky-300", chip: "bg-sky-100 dark:bg-sky-500/15" },
  sensing: { icon: ScanFace, tint: "text-violet-600 dark:text-violet-300", chip: "bg-violet-100 dark:bg-violet-500/15" },
  condition: { icon: GitBranch, tint: "text-amber-600 dark:text-amber-300", chip: "bg-amber-100 dark:bg-amber-500/15" },
  agent: { icon: Brain, tint: "text-indigo-600 dark:text-indigo-300", chip: "bg-indigo-100 dark:bg-indigo-500/15" },
  subagent: { icon: CirclePlay, tint: "text-rose-600 dark:text-rose-300", chip: "bg-rose-100 dark:bg-rose-500/15" },
  output: { icon: Send, tint: "text-teal-600 dark:text-teal-300", chip: "bg-teal-100 dark:bg-teal-500/15" },
  log: { icon: FileText, tint: "text-slate-500 dark:text-slate-300", chip: "bg-slate-100 dark:bg-slate-500/15" },
  end: { icon: Flag, tint: "text-slate-500 dark:text-slate-300", chip: "bg-slate-100 dark:bg-slate-500/15" },
};

// The adapter's icon reads better as a pen than a second brain.
const ICON_OVERRIDE: Record<string, LucideIcon> = { content_adapter: PenLine };

const STATUS_LABEL: Record<StepData["status"], string> = {
  idle: "waiting",
  running: "running",
  done: "done",
  error: "error",
  skipped: "not on this route",
};

/** The card itself, free of React Flow so it can be rendered and tested on its own. */
export function WorkflowStepCard({ data, selected }: { data: StepData; selected?: boolean }) {
  const style = KIND_STYLE[data.kind];
  const Icon = ICON_OVERRIDE[data.id] ?? style.icon;
  const isTerminal = data.kind === "trigger" || data.kind === "end";

  return (
    <div
      role="group"
      aria-label={`${data.title}: ${STATUS_LABEL[data.status]}`}
      data-status={data.status}
      style={{ width: STEP_WIDTH }}
      className={cn(
        "rounded-2xl border bg-card px-3.5 py-3 text-left shadow-sm transition-all duration-300",
        data.stub && "border-dashed",
        data.status === "done" && "border-success/50 shadow-success/10",
        data.status === "running" && "border-primary ring-4 ring-primary/20 shadow-md",
        data.status === "error" && "border-error ring-4 ring-error/15",
        (data.status === "idle" || data.status === "skipped") && "border-border",
        data.status === "skipped" && "opacity-50",
        selected && "ring-2 ring-primary/60",
      )}
    >
      <div className="flex items-start gap-2.5">
        <span
          className={cn("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", style.chip)}
          aria-hidden="true"
        >
          <Icon className={cn("h-4 w-4", style.tint)} />
        </span>
        <div className="min-w-0 flex-1">
          <p className={cn("text-[11px] font-semibold uppercase tracking-wider", style.tint)}>
            {data.eyebrow}
          </p>
          <p className="text-sm font-semibold leading-snug text-foreground">{data.title}</p>
        </div>
        <StatusIcon status={data.status} />
      </div>
      <div className="mt-2 flex items-center gap-2">
        <p
          className={cn("min-w-0 flex-1 truncate text-xs text-muted-foreground", isTerminal && "text-[11px]")}
          title={data.detail}
        >
          {data.detail}
        </p>
        {data.status === "done" && data.durationMs != null && !isTerminal ? (
          <span className="shrink-0 rounded-full bg-success/10 px-2 py-0.5 text-[11px] font-medium text-success">
            {fmtMs(data.durationMs)}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function StatusIcon({ status }: { status: StepData["status"] }) {
  if (status === "running")
    return <Loader className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />;
  if (status === "done")
    return <CircleCheck className="h-4 w-4 text-success" aria-hidden="true" />;
  if (status === "error")
    return <CircleAlert className="h-4 w-4 text-error" aria-hidden="true" />;
  return <span className="mt-1 h-2 w-2 rounded-full bg-border" aria-hidden="true" />;
}

export function ServiceBadgeCard({ data }: { data: ServiceData }) {
  const dot =
    data.healthy === true ? "bg-success" : data.healthy === false ? "bg-error" : "bg-muted/50";
  const state =
    data.healthy === true ? "healthy" : data.healthy === false ? "unreachable" : "no health signal";
  return (
    <div
      role="note"
      aria-label={`${data.label}: ${state}`}
      className="flex items-center gap-2 rounded-xl border border-border bg-surface/80 px-2.5 py-1.5 shadow-sm"
    >
      <Database className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
      <div className="min-w-0">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Service
        </p>
        <p className="whitespace-nowrap text-xs font-semibold text-foreground">{data.label}</p>
        <p className="whitespace-nowrap text-[11px] text-muted-foreground">{data.sublabel}</p>
      </div>
      <span className={cn("ml-1 h-2 w-2 shrink-0 rounded-full", dot)} title={state} />
    </div>
  );
}

// ── React Flow wrappers ─────────────────────────────────────────────────────────────

export type StepNode = Node<StepData, "step">;
export type ServiceNode = Node<ServiceData, "service">;

export function StepNodeView({ data, selected }: NodeProps<StepNode>) {
  const hideTarget = data.kind === "trigger";
  const hideSource = data.kind === "end";
  return (
    <>
      {!hideTarget && (
        <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-0 !bg-muted/60" />
      )}
      <WorkflowStepCard data={data} selected={selected} />
      {!hideSource && (
        <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border-0 !bg-muted/60" />
      )}
    </>
  );
}

export function ServiceNodeView({ data }: NodeProps<ServiceNode>) {
  return <ServiceBadgeCard data={data} />;
}
