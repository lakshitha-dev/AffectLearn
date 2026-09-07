"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";

interface SessionQuality {
  sessionId: string;
  learnerId: string | null;
  prompts: number;
  answered: number;
  skipped: number;
  skipRate: number | null;
  distinctLabels: number;
  dominantAffect: string | null;
  dominantShare: number | null;
  lowVariance: boolean;
  distribution: Record<string, number>;
}

interface QualitySummary {
  totalPrompts: number;
  answered: number;
  skipped: number;
  skipRate: number | null;
  distribution: Record<string, number>;
  sessions: SessionQuality[];
  flaggedSessions: number;
  fatigueCriteria: { minAnswers: number; dominantShare: number };
}

/** Same palette the designer analytics use, so an affect means one colour across the product. */
const AFFECT_COLOR: Record<string, string> = {
  engaged: "bg-green-500",
  confused: "bg-amber-500",
  bored: "bg-slate-400",
  frustrated: "bg-red-500",
  neutral: "bg-blue-400",
};

/**
 * Self-report label quality (Story 8.6 / FR48).
 *
 * The self-report widget is the pilot's ground-truth label source — everything the behavioural
 * result is validated against is a learner saying how they felt. Every prompt and response has
 * been recorded since Story 6.2, and nothing read them back to ask whether the labels are any
 * good. A participant who answers "engaged" to every prompt produces a dataset that looks clean
 * and measures nothing.
 *
 * Nothing here excludes a session. Deciding what to drop from an analysis belongs in the
 * analysis, where it can be written down and defended, not behind a toggle on an admin screen.
 */
export default function QualityPage() {
  const { data, isPending, isError } = useQuery<QualitySummary>({
    queryKey: ["selfReportQuality"],
    queryFn: () => apiFetch<QualitySummary>("/admin/research/self-report-quality"),
  });

  const pct = (value: number | null) =>
    value == null ? "—" : `${Math.round(value * 100)}%`;

  const totalLabels = Object.values(data?.distribution ?? {}).reduce((a, b) => a + b, 0);

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Label quality</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Whether the self-reports the behavioural result rests on are worth resting on.
        </p>
      </div>

      {isPending ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : isError || !data ? (
        <p className="text-sm text-muted-foreground">Could not load label quality.</p>
      ) : data.totalPrompts === 0 ? (
        <div className="rounded-lg border border-border bg-surface px-5 py-12 text-center">
          <p className="text-sm font-medium text-foreground">No self-reports recorded yet</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            Learners are prompted every few sections during a lesson. Their answers will appear
            here once sessions have run.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-4">
            {[
              { label: "Prompts shown", value: String(data.totalPrompts) },
              { label: "Answered", value: String(data.answered) },
              { label: "Skip rate", value: pct(data.skipRate) },
              { label: "Flagged sessions", value: String(data.flaggedSessions) },
            ].map((stat) => (
              <div key={stat.label} className="rounded-lg border border-border bg-surface p-4">
                <p className="text-sm text-muted-foreground">{stat.label}</p>
                <p className="mt-1 text-2xl font-bold text-foreground">{stat.value}</p>
              </div>
            ))}
          </div>

          <section className="rounded-lg border border-border bg-surface p-6">
            <h2 className="font-semibold text-foreground">Label distribution</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              A distribution concentrated on one state is the signature of a widget being clicked
              through rather than answered.
            </p>
            <ul className="mt-4 space-y-2">
              {Object.entries(data.distribution)
                .sort((a, b) => b[1] - a[1])
                .map(([affect, count]) => (
                  <li key={affect} className="flex items-center gap-3">
                    <span className="w-24 text-sm capitalize text-foreground">{affect}</span>
                    <span className="h-2 flex-1 overflow-hidden rounded-full bg-border">
                      <span
                        className={`block h-2 rounded-full ${AFFECT_COLOR[affect] ?? "bg-primary"}`}
                        style={{
                          width: totalLabels ? `${(count / totalLabels) * 100}%` : "0%",
                        }}
                      />
                    </span>
                    <span className="w-20 text-right text-sm text-muted-foreground">
                      {count} ({totalLabels ? Math.round((count / totalLabels) * 100) : 0}%)
                    </span>
                  </li>
                ))}
            </ul>
          </section>

          <section className="rounded-lg border border-border bg-surface p-6">
            <h2 className="font-semibold text-foreground">Sessions</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Flagged sessions first. A session is flagged when at least{" "}
              {data.fatigueCriteria.minAnswers} prompts were answered and at least{" "}
              {Math.round(data.fatigueCriteria.dominantShare * 100)}% of the answers were the same
              state. That is a heuristic, not a verdict — it may equally describe a genuinely
              consistent session.
            </p>

            <div className="mt-4 overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-border text-left">
                    <th className="py-2 pr-4 font-medium text-muted-foreground">Session</th>
                    <th className="py-2 pr-4 font-medium text-muted-foreground">Answered</th>
                    <th className="py-2 pr-4 font-medium text-muted-foreground">Skipped</th>
                    <th className="py-2 pr-4 font-medium text-muted-foreground">Labels used</th>
                    <th className="py-2 pr-4 font-medium text-muted-foreground">Most common</th>
                    <th className="py-2 font-medium text-muted-foreground">Review</th>
                  </tr>
                </thead>
                <tbody>
                  {data.sessions.map((session) => (
                    <tr key={session.sessionId} className="border-b border-border/60">
                      <td className="py-2 pr-4 font-mono text-xs text-foreground">
                        {session.sessionId}
                      </td>
                      <td className="py-2 pr-4 text-muted-foreground">{session.answered}</td>
                      <td className="py-2 pr-4 text-muted-foreground">
                        {session.skipped} ({pct(session.skipRate)})
                      </td>
                      <td className="py-2 pr-4 text-muted-foreground">
                        {session.distinctLabels}
                      </td>
                      <td className="py-2 pr-4 text-muted-foreground">
                        {session.dominantAffect ?? "—"}
                        {session.dominantShare != null && (
                          <span className="ml-1 text-xs">({pct(session.dominantShare)})</span>
                        )}
                      </td>
                      <td className="py-2">
                        {session.lowVariance ? (
                          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                            Low label variance
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
