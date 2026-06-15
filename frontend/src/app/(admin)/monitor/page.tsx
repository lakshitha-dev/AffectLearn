"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMonitorStream } from "@/hooks/use-monitor-stream";
import { AffectStream } from "@/components/monitor/AffectStream";
import { BehaviorPanel } from "@/components/monitor/BehaviorPanel";
import { CycleTimeline } from "@/components/monitor/CycleTimeline";
import { EventLog } from "@/components/monitor/EventLog";
import { FacialPanel } from "@/components/monitor/FacialPanel";
import { MetricsBar } from "@/components/monitor/MetricsBar";
import { PipelineFlow } from "@/components/monitor/PipelineFlow";
import { SessionPicker } from "@/components/monitor/SessionPicker";
import type { GraphTopology, MonitorHealth, MonitorSessions } from "@/types/monitor";

export default function MonitorPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);

  const graphQ = useQuery({
    queryKey: ["monitor", "graph"],
    queryFn: () => apiFetch<GraphTopology>("/monitor/graph"),
    staleTime: Infinity,
  });
  const healthQ = useQuery({
    queryKey: ["monitor", "health"],
    queryFn: () => apiFetch<MonitorHealth>("/monitor/health"),
    refetchInterval: 5000,
  });
  const sessionsQ = useQuery({
    queryKey: ["monitor", "sessions"],
    queryFn: () => apiFetch<MonitorSessions>("/monitor/sessions"),
    refetchInterval: 5000,
  });

  const stream = useMonitorStream(sessionId);
  const facialAvailable = healthQ.data?.models.facial.available;
  const sessionIds = sessionsQ.data?.recent_session_ids ?? [];
  const connected = stream.status === "open";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Pipeline Monitor</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Live observability for affect detection, behavior analysis, and the agent graph.
          </p>
        </div>
        <SessionPicker value={sessionId} onChange={setSessionId} sessionIds={sessionIds} />
      </div>

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
              <CardTitle className="text-base">Engagement / Affect Stream</CardTitle>
            </CardHeader>
            <CardContent>
              <AffectStream series={stream.affectSeries} />
            </CardContent>
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Behavior Analysis</CardTitle>
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
  );
}
