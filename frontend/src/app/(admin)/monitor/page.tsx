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
} from "@/hooks/use-monitor";
import { AffectStream } from "@/components/monitor/AffectStream";
import { BehaviorPanel } from "@/components/monitor/BehaviorPanel";
import { CycleTimeline } from "@/components/monitor/CycleTimeline";
import { EventLog } from "@/components/monitor/EventLog";
import { FacePresenceStrip } from "@/components/monitor/FacePresenceStrip";
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
  const decision = healthQ.data?.models.decision;

  // The Live tab's calibration verdict needs the windowed distribution, which only the aggregate
  // endpoint computes. Cheap (30s poll) and shared with the Aggregate tab's query cache.
  const aggQ = useMonitorAggregates(24);
  const facialStats = aggQ.data?.modalityStats?.facial;
  // The per-cycle panels show the LAST event received, with no notion of when. Without this they
  // render an ended session exactly like a live one -- which is what made a monitor report a
  // learner at 100% face presence with no camera open.
  const stale = stream.metrics.sessionState !== "active";

  // Which session ids are actually connected right now. `sessions.active` was fetched and
  // discarded, so a dead id in the picker looked identical to a live one.
  const activeIds = new Set(
    (sessionsQ.data?.active ?? []).map((a) => a.session_id).filter(Boolean) as string[],
  );

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
              behavioural: {behavioralKind ?? "—"} · facial: {facialKind ?? "—"}
              {/* Actionable states come from the live config, not a literal — a deploy that
                  changes ADAPT_STATES used to leave this caption quietly wrong. */}
              {decision?.adaptStates?.length
                ? ` · actionable: ${decision.adaptStates.join(", ")}`
                : null}
                  {decision?.channelMinConfidence &&
    Object.keys(decision.channelMinConfidence).length > 0 ? (
      // Per-channel floors. A single global number misdescribes any channel with an override:
      // the geometry channel gates at 0.70 while the global sits at 0.50, so this line used to
      // quote a threshold that channel is never measured against.
      <> · gates {Object.entries(decision.channelMinConfidence)
        .map(([k, v]) => `${k.replace("_model", "").replace("facial_", "")} ${v}`)
        .join(", ")}</>
    ) : decision?.adaptMinConfidence != null ? (
      <> · gate {decision.adaptMinConfidence}</>
    ) : null}
    {decision?.decisiveAffectSources?.length ? (
      <> · decisive: {decision.decisiveAffectSources.join(", ")}</>
    ) : null}
              {decision?.forcedMode && decision.forcedMode !== "auto" ? (
                <span className="ml-1 rounded bg-amber-100 px-1 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                  mode forced: {decision.forcedMode}
                </span>
              ) : null}
            </p>
          )}
        </div>
        <SessionPicker
          value={sessionId}
          onChange={setSessionId}
          sessionIds={sessionIds}
          activeIds={activeIds}
        />
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
                    <CardContent className="space-y-4">
                      <AffectStream series={stream.affectSeries} />
                      <FacePresenceStrip
                        series={stream.facePresenceSeries}
                        stale={stale}
                        lastCycleAgeMs={stream.metrics.lastCycleAgeMs}
                      />
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
                        <FacialPanel
                          data={stream.facial}
                          modelAvailable={facialAvailable}
                          stats={facialStats}
                          threshold={aggQ.data?.adaptMinConfidence}
                          stale={stale}
                          lastCycleAgeMs={stream.metrics.lastCycleAgeMs}
                        />
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
            <MonitorAggregates sessionId={sessionId} />
          )
        }
      </Tabs>
    </div>
  );
}
