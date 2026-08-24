"use client";

/**
 * Real component health, replacing a hardcoded mock.
 *
 * The previous version was a literal array of six services with invented latencies and
 * "99.98% uptime" figures. Nothing measured those numbers, and it rendered green regardless of
 * actual state — including while vLLM was unreachable in production. Everything here now comes
 * from GET /monitor/health.
 *
 * Uptime and latency are deliberately ABSENT rather than estimated: nothing in the stack tracks
 * them today, and a plausible-looking fabricated number is worse than an honest omission.
 */

import { useMonitorHealth } from "@/hooks/use-monitor";
import type { ModelReport, OnnxIo } from "@/types/monitor";

function Dot({ ok, pulse }: { ok: boolean; pulse?: boolean }) {
  return (
    <span
      className={
        "h-2 w-2 shrink-0 rounded-full " +
        (ok ? "bg-green-500" : pulse ? "bg-red-500 animate-pulse" : "bg-red-500")
      }
    />
  );
}

function Row({
  name,
  ok,
  detail,
  note,
}: {
  name: string;
  ok: boolean;
  detail?: string;
  note?: string;
}) {
  return (
    <tr className="border-b border-border last:border-0 align-top">
      <td className="px-4 py-3 font-medium text-foreground">{name}</td>
      <td className="px-4 py-3">
        <span
          className={
            "flex items-center gap-2 text-sm font-medium " +
            (ok ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400")
          }
        >
          <Dot ok={ok} pulse />
          {ok ? "OK" : "Unavailable"}
        </span>
      </td>
      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{detail ?? "—"}</td>
      <td className="px-4 py-3 text-xs text-muted-foreground">{note ?? ""}</td>
    </tr>
  );
}

function io(list?: OnnxIo[]): string {
  if (!list || list.length === 0) return "";
  return list.map((x) => "[" + x.shape.map((d) => (d == null ? "?" : d)).join(",") + "]").join(" ");
}

function modelDetail(m?: ModelReport): string {
  if (!m) return "—";
  if (m.error) return m.error;
  const shape = io(m.inputs) && io(m.outputs) ? io(m.inputs) + " → " + io(m.outputs) : "";
  return [m.kind ?? "kind unresolved", shape].filter(Boolean).join("  ");
}

export default function SystemHealthPage() {
  const { data, isPending, isError, error, refetch } = useMonitorHealth();

  if (isPending) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-foreground">System Health</h1>
        <div
          role="status"
          aria-label="Loading system health"
          className="mt-8 h-64 animate-pulse rounded-lg bg-border"
        />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-foreground">System Health</h1>
        <div className="mt-8 rounded-lg border border-border bg-surface p-6">
          <p className="text-sm text-foreground">
            Health unavailable{error ? ": " + (error as Error).message : ""}
          </p>
          <button
            onClick={() => refetch()}
            className="mt-3 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-accent"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const beh = data.models.behavioral;
  const fac = data.models.facial;
  const llm = data.llm;
  const dec = data.models.decision;

  const checks = [
    { name: "Database (PostgreSQL)", ok: data.database.ok },
    { name: "Redis", ok: data.redis.enabled },
    { name: "Behavioural model", ok: Boolean(beh?.available) },
    { name: "Facial model", ok: Boolean(fac?.available) },
    { name: "vLLM (adaptation generation)", ok: Boolean(llm?.reachable) },
  ];
  const okCount = checks.filter((c) => c.ok).length;
  const allOk = okCount === checks.length;

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">System Health</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Live component status from <code>/monitor/health</code>. Uptime and latency are not
          tracked and are therefore not shown.
        </p>
      </div>

      <div
        className={
          "mb-6 flex items-start gap-3 rounded-lg border px-5 py-4 " +
          (allOk
            ? "border-green-200 bg-green-50 dark:border-green-800/40 dark:bg-green-900/10"
            : "border-amber-200 bg-amber-50 dark:border-amber-800/40 dark:bg-amber-900/10")
        }
      >
        <span
          className={
            "mt-1 h-2.5 w-2.5 shrink-0 rounded-full " + (allOk ? "bg-green-500" : "bg-amber-500")
          }
        />
        <div>
          <p
            className={
              "text-sm font-semibold " +
              (allOk
                ? "text-green-800 dark:text-green-400"
                : "text-amber-800 dark:text-amber-400")
            }
          >
            {okCount}/{checks.length} components healthy
          </p>
          {llm && !llm.reachable ? (
            <p className="mt-0.5 text-xs text-amber-700 dark:text-amber-500">
              vLLM is unreachable, so adaptations are served from the deterministic rule-based
              fallback rather than generated. Detection and the adaptation gate are unaffected.
            </p>
          ) : null}
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border bg-surface">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b border-border bg-background">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Component</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Resolved</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Notes</th>
            </tr>
          </thead>
          <tbody>
            <Row name="Database (PostgreSQL)" ok={data.database.ok} />
            <Row
              name="Redis"
              ok={data.redis.enabled}
              note="research event stream + learner profile cache"
            />
            <Row
              name="Behavioural model"
              ok={Boolean(beh?.available)}
              detail={modelDetail(beh)}
              note={beh?.path}
            />
            <Row
              name="Facial model"
              ok={Boolean(fac?.available)}
              detail={modelDetail(fac)}
              // When it is missing, the DEGRADATION is the useful note, not the path.
              note={
                fac?.available
                  ? fac.path
                  : "degrades to behavioural-only when absent" +
                    (fac?.path ? " — " + fac.path : "")
              }
            />
            <Row
              name="vLLM (adaptation generation)"
              ok={Boolean(llm?.reachable)}
              detail={llm ? llm.model : "—"}
              note={
                llm
                  ? llm.reachable
                    ? llm.endpoint
                    : (llm.error ?? "unreachable") + " — " + llm.endpoint
                  : ""
              }
            />
            <Row
              name="WebSocket gateway"
              ok
              detail={data.websocket.active_connections + " active"}
              note="one connection per learner; a second closes the first"
            />
            <Row
              name="Monitor bus"
              ok
              detail={
                data.monitor.subscribers +
                " subscriber(s), " +
                data.monitor.buffered_events +
                " buffered"
              }
              note="in-process ring buffer; ephemeral"
            />
          </tbody>
        </table>
      </div>

      {dec && !dec.error ? (
        <div className="mt-6 rounded-lg border border-border bg-surface p-6">
          <h2 className="text-sm font-semibold text-foreground">Adaptation gate configuration</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            The thresholds that decide whether a detection becomes an intervention.
          </p>
          <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[
              ["Actionable states", (dec.adaptStates ?? []).join(", ") || "—"],
              ["Min confidence", String(dec.adaptMinConfidence ?? "—")],
              ["Min consecutive", String(dec.adaptMinConsecutive ?? "—")],
              ["Cooldown cycles", String(dec.adaptCooldownCycles ?? "—")],
              ["Fusion drives decision", dec.fusionDrivesDecision ? "yes" : "no"],
              ["Forced mode", dec.forcedMode ?? "auto"],
            ].map(([k, v]) => (
              <div key={k} className="rounded-md border border-border px-3 py-2">
                <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{k}</dt>
                <dd className="font-mono text-sm text-foreground">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
    </div>
  );
}
