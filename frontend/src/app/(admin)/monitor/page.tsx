"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";
import { useMonitorStream } from "@/hooks/use-monitor-stream";
import {
  useMonitorAggregates,
  useMonitorGraph,
  useMonitorHealth,
  useMonitorSessions,
  useSessionHistory,
} from "@/hooks/use-monitor";
import { AffectStream } from "@/components/monitor/AffectStream";
import { AgentFlow } from "@/components/monitor/AgentFlow";
import { AgentWorkflowGraph } from "@/components/monitor/AgentWorkflowGraph";
import { CurrentDetection } from "@/components/monitor/CurrentDetection";
import { DetectionTimeline } from "@/components/monitor/DetectionTimeline";
import { BehaviorPanel } from "@/components/monitor/BehaviorPanel";
import { CycleTimeline } from "@/components/monitor/CycleTimeline";
import { EventLog } from "@/components/monitor/EventLog";
import { InterventionLifecycle } from "@/components/monitor/InterventionLifecycle";
import { SessionOverview } from "@/components/monitor/SessionOverview";
import { FacePresenceStrip } from "@/components/monitor/FacePresenceStrip";
import { FacialPanel } from "@/components/monitor/FacialPanel";
import { MetricsBar } from "@/components/monitor/MetricsBar";
import { MonitorAggregates } from "@/components/monitor/MonitorAggregates";
import { ConfigChips, LiveStatusPill } from "@/components/monitor/MonitorHeader";
import { SessionPicker } from "@/components/monitor/SessionPicker";

// Overview first: the question an operator opens this page with is "what is the system doing
// right now", and the workflow graph answers it at a glance. The detail views follow.
const TABS = [
  { value: "overview", label: "Overview" },
  { value: "signals", label: "Signals" },
  { value: "events", label: "Events" },
  { value: "aggregate", label: "Aggregate" },
];

/** One panel: a titled card. Titles render as real headings (see `CardTitle`). */
function Panel({
  title,
  subtitle,
  className,
  children,
}: {
  title: string;
  subtitle?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{title}</CardTitle>
        {subtitle ? <p className="text-sm text-muted-foreground">{subtitle}</p> : null}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export default function MonitorPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);

  const graphQ = useMonitorGraph();
  const healthQ = useMonitorHealth();
  const sessionsQ = useMonitorSessions();

  // The stream stays mounted across tab switches (the Tabs panels hide rather than unmount),
  // so switching tabs does not drop the SSE backlog.
  const stream = useMonitorStream(sessionId);
  const facialAvailable = healthQ.data?.models.facial.available;
  const sessionIds = sessionsQ.data?.recent_session_ids ?? [];
  const connected = stream.status === "open";

  const behavioralKind = healthQ.data?.models.behavioral.kind;
  const facialKind = healthQ.data?.models.facial.kind;
  const decision = healthQ.data?.models.decision;

  // The facial calibration verdict needs the windowed distribution, which only the aggregate
  // endpoint computes. Cheap (30s poll) and shared with the Aggregate tab's query cache.
  const aggQ = useMonitorAggregates(24);
  const facialStats = aggQ.data?.modalityStats?.facial;
  // The per-cycle panels show the LAST event received. Without this they render an ended session
  // exactly like a live one.
  const stale = stream.metrics.sessionState !== "active";

  const activeIds = new Set(
    (sessionsQ.data?.active ?? []).map((a) => a.session_id).filter(Boolean) as string[],
  );

  // The history panels are per-session: with no explicit choice they follow the one active
  // session when exactly one is active, and otherwise ask for a choice rather than guessing.
  const soleActiveId = activeIds.size === 1 ? [...activeIds][0] : null;
  const historySessionId = sessionId ?? soleActiveId;

  // The DATABASE-backed view of this session: the SSE ring holds only ~7-10 cycles.
  const historyQ = useSessionHistory(historySessionId);
  const history = historyQ.data;
  const changes = history?.stateChanges ?? [];
  const cycles = history?.cycles ?? [];
  const latestCycle = cycles.length ? cycles[cycles.length - 1] : null;
  const currentRun = changes.length ? changes[changes.length - 1] : null;
  const timeInStateMs =
    currentRun?.at != null && !stale ? Date.now() - currentRun.at : currentRun?.durationMs ?? null;

  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-border bg-card p-5 shadow-sm">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">Pipeline Monitor</h1>
            <LiveStatusPill
              sessionState={stream.metrics.sessionState}
              connected={connected}
              sessionId={historySessionId}
              lastCycleAgeMs={stream.metrics.lastCycleAgeMs}
            />
          </div>
          <p className="text-sm text-muted-foreground">
            Watch each learner cycle move through detection, the adaptation gate and the agents.
          </p>
          {/* The artifacts actually loaded and the live gate settings, read from the server. */}
          <ConfigChips behavioralKind={behavioralKind} facialKind={facialKind} decision={decision} />
        </div>
        <SessionPicker
          value={sessionId}
          onChange={setSessionId}
          sessionIds={sessionIds}
          activeIds={activeIds}
        />
      </header>

      <Tabs tabs={TABS} defaultValue="overview">
        {(active) => {
          if (active === "overview")
            return (
              <div className="space-y-6">
                <MetricsBar metrics={stream.metrics} health={healthQ.data} connected={connected} />

                <Panel
                  title="Agent Workflow"
                  subtitle="The live agent graph. The route the last cycle took is highlighted; click a step for details."
                >
                  <AgentWorkflowGraph
                    topology={graphQ.data}
                    nodeStates={stream.nodeStates}
                    lastRoute={stream.lastRoute}
                    cycle={latestCycle}
                    health={healthQ.data}
                    live={!stale}
                  />
                </Panel>

                <div className="grid gap-6 xl:grid-cols-2">
                  <Panel title="Current Detection">
                    <CurrentDetection
                      facial={stream.facial}
                      behavioral={stream.behavioral}
                      fusion={stream.fusion}
                      channelFloors={decision?.channelMinConfidence}
                      stale={stale}
                      lastCycleAgeMs={stream.metrics.lastCycleAgeMs}
                      timeInStateMs={timeInStateMs}
                      fusionDrives={decision?.fusionDrivesDecision}
                    />
                  </Panel>
                  <Panel title="Interventions">
                    {historySessionId ? (
                      <InterventionLifecycle
                        interventions={history?.interventions ?? []}
                        loading={historyQ.isLoading}
                      />
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        Select a session to see its interventions.
                      </p>
                    )}
                  </Panel>
                </div>

                <Panel
                  title="Last cycle, step by step"
                  subtitle={
                    latestCycle
                      ? `Cycle #${latestCycle.cycle_number}, from the research record`
                      : undefined
                  }
                >
                  <AgentFlow
                    cycle={latestCycle}
                    cycleLabel={
                      latestCycle
                        ? `cycle #${latestCycle.cycle_number} — most recent recorded`
                        : undefined
                    }
                    fusionDrives={decision?.fusionDrivesDecision}
                  />
                </Panel>

                {historySessionId && history?.summary ? (
                  <SessionOverview summary={history.summary} live={!stale} />
                ) : null}
              </div>
            );

          if (active === "signals")
            return (
              <div className="space-y-6">
                <Panel title="Affect Stream">
                  <div className="space-y-4">
                    <AffectStream series={stream.affectSeries} />
                    <FacePresenceStrip
                      series={stream.facePresenceSeries}
                      stale={stale}
                      lastCycleAgeMs={stream.metrics.lastCycleAgeMs}
                    />
                  </div>
                </Panel>
                <div className="grid gap-6 lg:grid-cols-2">
                  <Panel title="Facial Analysis">
                    <FacialPanel
                      data={stream.facial}
                      modelAvailable={facialAvailable}
                      stats={facialStats}
                      threshold={aggQ.data?.adaptMinConfidence}
                      stale={stale}
                      lastCycleAgeMs={stream.metrics.lastCycleAgeMs}
                    />
                  </Panel>
                  <Panel title="Behaviour Analysis">
                    <BehaviorPanel data={stream.behavioral} />
                  </Panel>
                </div>
                <Panel title="Cycle Timeline">
                  <CycleTimeline events={stream.events} />
                </Panel>
              </div>
            );

          if (active === "events")
            return (
              <div className="grid gap-6 xl:grid-cols-5">
                <Panel title="Detection Timeline" className="xl:col-span-3">
                  {historySessionId ? (
                    <DetectionTimeline
                      changes={changes}
                      cycles={cycles}
                      loading={historyQ.isLoading}
                    />
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      Select a session to see its detection history. The timeline is read from the
                      research record, not the live stream, so it covers the whole session.
                    </p>
                  )}
                </Panel>
                <Panel title="Live Event Log" className="xl:col-span-2">
                  <EventLog events={stream.events} />
                </Panel>
              </div>
            );

          return <MonitorAggregates sessionId={sessionId} />;
        }}
      </Tabs>
    </div>
  );
}
