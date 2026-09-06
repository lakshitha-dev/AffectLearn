"use client";

/**
 * A/B research groups — what the study allocation ACTUALLY is.
 *
 * This page previously rendered a hardcoded array: three conditions that do not exist in the
 * system (`control` / `webcam` / `behavioral`, where the real vocabulary is `control` /
 * `adaptive`), invented member counts of 12/11/13, and a claim that "learners are automatically
 * assigned to groups during registration based on a balanced randomization algorithm."
 *
 * No such algorithm exists. Nothing calls `assign_group` outside the admin route and its tests:
 * allocation is a manual `POST /admin/study/groups` per learner, and an account with no
 * assignment defaults to `control`. A research console that asserts a randomisation procedure it
 * does not perform is a methodological claim the thesis cannot support, so the page now reads the
 * real endpoints and states the real procedure.
 */

import { useMemo } from "react";

import { useStudyGroups, useStudyPhase } from "@/hooks/use-study";

const CONDITION_COLORS: Record<string, string> = {
  control: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  adaptive: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
};

const CONDITION_COPY: Record<string, string> = {
  control:
    "Detection runs and is logged, but no adaptation is ever delivered. Also the default for any account with no assignment.",
  adaptive:
    "Eligible to receive interventions, but only once the global phase is phase_b.",
};

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}

export default function ABGroupsPage() {
  const groupsQ = useStudyGroups();
  const phaseQ = useStudyPhase();

  const counts = useMemo(() => {
    const items = groupsQ.data?.items ?? [];
    const byGroup: Record<string, number> = { adaptive: 0, control: 0 };
    let locked = 0;
    for (const a of items) {
      byGroup[a.group] = (byGroup[a.group] ?? 0) + 1;
      if (a.lockedAt) locked += 1;
    }
    return { byGroup, locked, total: items.length };
  }, [groupsQ.data]);

  const phase = phaseQ.data?.phase;
  const interventionsPossible = phase === "phase_b";

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">A/B Research Groups</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Live allocation, read from the study record.
        </p>
      </div>

      {/* Phase gates everything below it: no learner in any group receives an intervention
          while the global phase is phase_a. Stating it first avoids reading the group counts
          as if they described who is currently being adapted. */}
      <div className="mb-6 rounded-lg border border-border bg-surface p-5">
        <h2 className="mb-1 font-semibold text-foreground">Study phase</h2>
        {phaseQ.isLoading ? (
          <Empty>Loading…</Empty>
        ) : phaseQ.isError ? (
          <Empty>Phase could not be read.</Empty>
        ) : (
          <p className="text-sm text-muted-foreground">
            <span className="font-mono text-foreground">{phase}</span>
            {phaseQ.data?.transitionedAt ? (
              <> · changed {new Date(phaseQ.data.transitionedAt).toLocaleString()}</>
            ) : (
              <> · never transitioned</>
            )}
            {" — "}
            {interventionsPossible
              ? "the adaptive group can receive interventions."
              : "no learner receives interventions in phase_a, in either group."}
          </p>
        )}
      </div>

      <div className="mb-8 grid gap-4 sm:grid-cols-2">
        {(["adaptive", "control"] as const).map((group) => (
          <div key={group} className="rounded-lg border border-border bg-surface p-5">
            <div className="mb-3 flex items-start justify-between">
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${CONDITION_COLORS[group]}`}
              >
                {group}
              </span>
              <span className="text-2xl font-bold tabular-nums text-foreground">
                {groupsQ.isLoading ? "—" : (counts.byGroup[group] ?? 0)}
              </span>
            </div>
            <p className="text-sm text-muted-foreground">{CONDITION_COPY[group]}</p>
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-border bg-surface p-6">
        <h2 className="mb-2 font-semibold text-foreground">Group assignment</h2>
        <p className="text-sm text-muted-foreground">
          Assignment is <strong className="text-foreground">manual</strong>: an admin issues{" "}
          <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
            POST /api/v1/admin/study/groups
          </code>{" "}
          per learner. There is no automatic or balanced allocation, and an account with no
          assignment defaults to <span className="font-mono">control</span>. Assignment is keyed to
          the account rather than the device, so the same learner on two devices stays in one group.
        </p>
        <p className="mt-3 text-sm text-muted-foreground">
          {groupsQ.isLoading
            ? "Loading assignments…"
            : groupsQ.isError
              ? "Assignments could not be read."
              : counts.total === 0
                ? "No learners have been assigned yet."
                : `${counts.total} assigned · ${counts.locked} locked.`}
        </p>

        {/* Locking is the "the pilot has begun" gate: once locked, an assignment can no longer be
            corrected, which is what stops a participant being moved between conditions mid-study. */}
        {!groupsQ.isLoading && !groupsQ.isError && counts.total > 0 && counts.locked === 0 ? (
          <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-800/40 dark:bg-amber-900/20">
            <p className="text-sm text-amber-700 dark:text-amber-400">
              Assignments are unlocked, so they can still be changed. Lock them before data
              collection begins — moving a participant between conditions mid-study invalidates
              their data.
            </p>
          </div>
        ) : null}
      </div>

      <p className="mt-6 text-xs text-muted-foreground">
        Note: the randomisation in this study is at the <strong>intervention</strong> level, not
        the participant level. Within the adaptive group, every cycle that clears the adaptation
        gate is randomly either delivered or withheld, and the withheld cycles are the matched
        control the delivered ones are compared against.
      </p>
    </div>
  );
}
