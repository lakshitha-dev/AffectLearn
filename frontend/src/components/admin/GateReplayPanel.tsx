"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api-client";

interface ReplayRow {
  minConfidence: number;
  interventions: number;
  cycles: number;
  interventionsPerHour: number | null;
  gateReasons: Record<string, number>;
  precision: number | null;
  matchedInterventions: number;
  warrantedInterventions: number;
}

interface ReplayResult {
  sessions: number;
  cycles: number;
  selfReports: number;
  heldFixed: {
    minConsecutive: number;
    cooldownCycles: number;
    decisiveSources: string[] | string | null;
    adaptStates: string[];
  };
  rows: ReplayRow[];
  caveat: string;
}

const DEFAULT_FLOORS = "0.50,0.55,0.60,0.65,0.70,0.75,0.80";

/**
 * Re-run the adaptation gate at other confidence floors over the recorded cycles.
 *
 * `GET /admin/research/gate-replay` was implemented, documented and reachable from nothing — the
 * data-export page listed it in prose as something "queried through the admin research API",
 * which in practice meant curl.
 *
 * This is the tool Section 4.5 of the paper argues for: the deployed floor of 0.70 sat above the
 * entire observed score range of the facial channel, so the channel never once contributed to an
 * intervention. A sweep is how you find that out from data rather than from a round number.
 */
export function GateReplayPanel() {
  const [floors, setFloors] = useState(DEFAULT_FLOORS);
  const [submitted, setSubmitted] = useState<string | null>(null);

  const { data, isPending, isError, error } = useQuery<ReplayResult>({
    queryKey: ["gateReplay", submitted],
    queryFn: () =>
      apiFetch<ReplayResult>(
        `/admin/research/gate-replay?floors=${encodeURIComponent(submitted ?? "")}`
      ),
    enabled: submitted !== null,
  });

  const pct = (value: number | null) =>
    value == null ? "—" : `${Math.round(value * 100)}%`;

  return (
    <div className="mb-6 rounded-lg border border-border bg-surface p-5">
      <h2 className="font-semibold text-foreground">Gate replay</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        What the adaptation gate would have done at other confidence floors, over the cycles
        already recorded. Nothing is changed by running this.
      </p>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <label className="text-xs text-muted-foreground">
          Confidence floors
          <input
            value={floors}
            onChange={(e) => setFloors(e.target.value)}
            className="mt-1 block h-9 w-80 rounded-md border border-border bg-background px-3 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </label>
        <Button size="sm" onClick={() => setSubmitted(floors)} disabled={isPending && !!submitted}>
          {submitted && isPending ? "Replaying…" : "Run sweep"}
        </Button>
      </div>

      {submitted && isError && (
        <p className="mt-4 text-sm text-muted-foreground">
          {(error as Error)?.message ?? "The replay failed."}
        </p>
      )}

      {data && (
        <div className="mt-5">
          <p className="text-xs text-muted-foreground">
            {data.sessions} session{data.sessions === 1 ? "" : "s"} · {data.cycles} cycles ·{" "}
            {data.selfReports} self-report{data.selfReports === 1 ? "" : "s"}. Held fixed:
            sustain {data.heldFixed.minConsecutive}, cooldown {data.heldFixed.cooldownCycles}{" "}
            cycles, states {data.heldFixed.adaptStates.join(", ")}.
          </p>

          {data.rows.length === 0 ? (
            <p className="mt-3 text-sm text-muted-foreground">
              No recorded cycles to replay yet.
            </p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-border text-left">
                    <th className="py-2 pr-4 font-medium text-muted-foreground">Floor</th>
                    <th className="py-2 pr-4 font-medium text-muted-foreground">Interventions</th>
                    <th className="py-2 pr-4 font-medium text-muted-foreground">Per hour</th>
                    <th className="py-2 pr-4 font-medium text-muted-foreground">Precision</th>
                    <th className="py-2 font-medium text-muted-foreground">Matched</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.minConfidence} className="border-b border-border/60">
                      <td className="py-2 pr-4 font-mono text-foreground">
                        {row.minConfidence.toFixed(2)}
                      </td>
                      <td className="py-2 pr-4 text-foreground">{row.interventions}</td>
                      <td className="py-2 pr-4 text-muted-foreground">
                        {row.interventionsPerHour ?? "—"}
                      </td>
                      <td className="py-2 pr-4 text-muted-foreground">{pct(row.precision)}</td>
                      <td className="py-2 text-muted-foreground">
                        {row.warrantedInterventions}/{row.matchedInterventions}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/*
            The caveat travels with the table because a sweep is exactly the kind of output that
            gets pasted into a chapter without it.
          */}
          <p className="mt-3 text-xs text-muted-foreground">{data.caveat}</p>
        </div>
      )}
    </div>
  );
}
