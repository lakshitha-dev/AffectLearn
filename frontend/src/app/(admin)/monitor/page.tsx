"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";
import { useMonitorStream } from "@/hooks/use-monitor-stream";
import { useMonitorGraph, useMonitorHealth, useMonitorSessions } from "@/hooks/use-monitor";
import { AffectStream } from "@/components/monitor/AffectStream";
import { BehaviorPanel } from "@/components/monitor/BehaviorPanel";
import { CycleTimeline } from "@/components/monitor/CycleTimeline";
import { EventLog } from "@/components/monitor/EventLog";
import { FacialPanel } from "@/components/monitor/FacialPanel";
import { MetricsBar } from "@/components/monitor/MetricsBar";
import { MonitorAggregates } from "@/components/monitor/MonitorAggregates";
import { PipelineFlow } from "@/components/monitor/PipelineFlow";
import { SessionPicker } from "@/components/monitor/SessionPicker";

const TABS = [
  { value: "live", label: "Live" },
  { value: "aggregate", label: "Aggregate" },
];

export default function MonitorPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);

  // Query hooks moved to `use-monitor.ts` — this page previously called apiFetch inline, the
  // only place in the app that bypassed the per-domain hook layer.
  const graphQ = useMonitorGraph();
  const healthQ = useMonitorHealth();
  const sessionsQ = useMonitorSessions();

  // The stream stays mounted across tab switches (the Tabs panels hide rather than unmount),
  // so switching to Aggregate and back does not drop the SSE backlog.
  const stream = useMonitorStream(sessionId);
  const facialAvailable = healthQ.data?.models.facial.available;
  const sessionIds = sessionsQ.data?.recent_session_ids ?? [];
  const connected = stream.status === "open";

  const behavioralKind = healthQ.data?.models.behavioral.kind;
  const facialKind = healthQ.data?.models.facial.kind;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Pipeline Monitor</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Live observability for affect detection, behaviour analysis, and the agent graph.
          </p>
          {/* Name the artifacts actually loaded. The panels below used to hardcode model names
              and kept saying "Bi-LSTM" for weeks after the GBDT replaced it. */}
          {(behavioralKind || facialKind) && (
            <p className="mt-1 font-mono text-[11px] text-muted-foreground">
              behavioural: {behavioralKind ?? "—"} · facial: {facialKind ?? "—"} · only{" "}
              <span className="font-semibold">confused</span> is detectable
            </p>
          )}
        </div>
        <SessionPicker value={sessionId} onChange={setSessionId} sessionIds={sessionIds} />
      </div>

      <Tabs tabs={TABS} defaultValue="live">
        {(active) =>
          active === "live" ? (
            <div className="space-y-5">
              <MetricsBar metrics={stream.metrics} health={healthQ.data} connected={connected} />

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Agent Execution Flow</CardTitle>
                </CardHeader>
                <CardContent>
                  <PipelineFlow
                    topology={graphQ.data}
                    nodeStates={stream.nodeStates}
                    lastRoute={stream.lastRoute}
                    facialAvailable={facialAvailable}
                  />
                </CardContent>
              </Card>

              <div className="grid gap-4 lg:grid-cols-3">
                <div className="space-y-4 lg:col-span-2">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Affect Stream</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <AffectStream series={stream.affectSeries} />
                    </CardContent>
                  </Card>

                  <div className="grid gap-4 md:grid-cols-2">
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">Behaviour Analysis</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <BehaviorPanel data={stream.behavioral} />
                      </CardContent>
                    </Card>
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-base">Facial Analysis</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <FacialPanel data={stream.facial} modelAvailable={facialAvailable} />
                      </CardContent>
                    </Card>
                  </div>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Cycle Timeline</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <CycleTimeline events={stream.events} />
                    </CardContent>
                  </Card>
                </div>

                <Card className="lg:row-span-2">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Live Event Log</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <EventLog events={stream.events} />
                  </CardContent>
                </Card>
              </div>
            </div>
          ) : (
            <MonitorAggregates />
          )
        }
      </Tabs>
    </div>
  );
}
