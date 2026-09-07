"use client";

/**
 * Data export — the exports that actually exist.
 *
 * This page previously listed five datasets with invented file sizes ("~2.4 MB", "~8.9 MB"),
 * every button `disabled` and titled "Connect to backend to enable exports". One of them,
 * "Pre/Post Assessment Results", has no endpoint behind it at all. A research console that
 * advertises datasets it cannot produce wastes the one resource a final-year project has least
 * of, so the list is now exactly what the API serves.
 */

import { useState } from "react";

import { exportMonitorCsv } from "@/hooks/use-monitor";
import { GateReplayPanel } from "@/components/admin/GateReplayPanel";

const WINDOWS = [
  { hours: 24, label: "Last 24 hours" },
  { hours: 168, label: "Last 7 days" },
  { hours: 720, label: "Last 30 days (max)" },
];

/** What the CSV carries, stated so nobody has to download it to find out. */
const CSV_COLUMNS =
  "timestamp, iso_time, session_id, learner_id, cycle_number, sequence_number, event_type, " +
  "phase, group, affect_state, confidence, p_confused, p_disengaged, model_kind, gate_reason, " +
  "forced_mode, action, fallback, section_id, adaptation_id, interaction, probe_response, arm";

export default function DataExportPage() {
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(hours: number) {
    setBusy(hours);
    setError(null);
    try {
      await exportMonitorCsv(hours);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Data Export</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Download the research event record for offline analysis.
        </p>
      </div>

      <div className="mb-6 rounded-lg border border-border bg-surface p-5">
        <h2 className="font-semibold text-foreground">Research events (CSV)</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          One row per recorded event, ordered by sequence number. This is the flat export the
          analysis is built from.
        </p>

        <div className="mt-4 flex flex-wrap gap-2">
          {WINDOWS.map((w) => (
            <button
              key={w.hours}
              type="button"
              onClick={() => run(w.hours)}
              disabled={busy !== null}
              className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
            >
              {busy === w.hours ? "Preparing…" : w.label}
            </button>
          ))}
        </div>

        {error ? (
          <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>
        ) : null}

        <details className="mt-4">
          <summary className="cursor-pointer text-xs text-muted-foreground">Columns</summary>
          <p className="mt-2 break-words font-mono text-[11px] text-muted-foreground">
            {CSV_COLUMNS}
          </p>
        </details>
      </div>

      {/* The trial contrast is the reason this file exists, so how to compute it is stated here
          rather than left to be rediscovered from column names. */}
      <div className="mb-6 rounded-lg border border-border bg-surface p-5">
        <h2 className="font-semibold text-foreground">Reading the trial columns</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Filter to <span className="font-mono">event_type = learner_profile_updated</span> and a
          non-empty <span className="font-mono">arm</span>. Those rows are the cycles that cleared
          every gate condition; <span className="font-mono">delivered</span> and{" "}
          <span className="font-mono">withheld</span> are matched by construction, so they are the
          comparison. A blank <span className="font-mono">arm</span> means the cycle never became
          eligible — it is <strong className="text-foreground">not</strong> a control observation
          and including it would bias the contrast.
        </p>
        <p className="mt-3 text-sm text-muted-foreground">
          <span className="font-mono">probe_response</span> distinguishes{" "}
          <span className="font-mono">dismissed</span> (the learner was asked and declined) from{" "}
          <span className="font-mono">did_not_help</span> (the learner judged it unhelpful).
          Collapsing the two would manufacture negative evidence.
        </p>
      </div>

      {/*
        Was listed here in prose as something "queried through the admin research API", which in
        practice meant curl. It is the tool the deployment observations argue for, so it belongs
        on the screen rather than in a sentence about the screen.
      */}
      <GateReplayPanel />

      <div className="rounded-lg border border-border bg-surface p-5">
        <h2 className="font-semibold text-foreground">Other datasets</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Queried through the admin research API rather than downloaded here:{" "}
          <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
            /api/v1/admin/research/events
          </code>{" "}
          (filterable by learner, session, phase, group, event type, course and section),{" "}
          <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
            /phase-a-dataset
          </code>{" "}
          (behavioural windows with self-report labels). Gate replay now has its own panel
          above.
        </p>
        <p className="mt-3 text-sm text-muted-foreground">
          There is no pre/post assessment export. Assessment attempts are module-scoped and live in
          the application tables, not the event record.
        </p>
      </div>

      <p className="mt-6 text-xs text-muted-foreground">
        Exports carry pseudonymous learner and session identifiers — no names or email addresses.
        The identifiers are stable, so they still re-identify a participant if joined against the
        user table; treat the files as personal data.
      </p>
    </div>
  );
}
