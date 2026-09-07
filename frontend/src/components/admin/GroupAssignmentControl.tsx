"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAdminUsers } from "@/hooks/use-admin-users";
import {
  useAssignGroup,
  useLockAssignments,
  useStudyGroups,
  type StudyGroupName,
} from "@/hooks/use-study";
import { ApiRequestError } from "@/lib/api-client";

/**
 * Assign learners to study conditions, and lock the cohorts (Story 8.2 / FR32).
 *
 * `POST /admin/study/groups` and `/groups/lock` both existed and neither was ever called — while
 * the admin settings page told administrators to "Change them from A/B Groups", a page with no
 * controls on it. A console that points at a screen which cannot do the thing is worse than one
 * that admits the gap.
 *
 * Allocation is manual and this page says so. There is no randomisation procedure in the system;
 * an account with no assignment defaults to `control` at read time, which is a fact the audit
 * panel surfaces rather than something this control quietly compensates for.
 */
export function GroupAssignmentControl() {
  const groupsQuery = useStudyGroups();
  const usersQuery = useAdminUsers({ page: 1, pageSize: 100, role: "learner" });
  const assign = useAssignGroup();
  const lock = useLockAssignments();
  const [confirmLock, setConfirmLock] = useState(false);

  const assignments = groupsQuery.data?.items ?? [];
  const byUser = new Map(assignments.map((a) => [a.userId, a]));
  const locked = assignments.some((a) => a.lockedAt);
  const learners = usersQuery.data?.items ?? [];

  async function setGroup(userId: string, group: StudyGroupName) {
    try {
      await assign.mutateAsync({ userId, group });
      toast.success(`Assigned to ${group}`);
    } catch (err) {
      toast.error(
        err instanceof ApiRequestError && err.errorCode === "GROUP_LOCKED"
          ? "Assignments are locked — the pilot has begun."
          : "Could not assign the group."
      );
    }
  }

  async function doLock() {
    try {
      await lock.mutateAsync();
      toast.success("Cohorts locked. Assignments can no longer be changed.");
      setConfirmLock(false);
    } catch {
      toast.error("Could not lock the assignments.");
    }
  }

  return (
    <section className="mt-8 rounded-lg border border-border bg-surface p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="font-semibold text-foreground">Allocation</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Assignment is manual — there is no randomisation procedure in the system. An
            unassigned account is treated as <span className="font-mono text-xs">control</span>.
          </p>
        </div>
        {locked ? (
          <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
            Locked
          </span>
        ) : (
          <Button size="sm" variant="outline" onClick={() => setConfirmLock(true)}>
            Lock cohorts
          </Button>
        )}
      </div>

      {usersQuery.isPending ? (
        <p className="mt-4 text-sm text-muted-foreground">Loading learners…</p>
      ) : learners.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          No learner accounts to allocate yet.
        </p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="py-2 pr-4 font-medium text-muted-foreground">Learner</th>
                <th className="py-2 pr-4 font-medium text-muted-foreground">Group</th>
                <th className="py-2 font-medium text-muted-foreground">Assign</th>
              </tr>
            </thead>
            <tbody>
              {learners.map((learner) => {
                const current = byUser.get(learner.id);
                return (
                  <tr key={learner.id} className="border-b border-border/60">
                    <td className="py-2 pr-4">
                      <span className="text-foreground">
                        {learner.firstName} {learner.lastName}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {learner.emailAddress}
                      </span>
                    </td>
                    <td className="py-2 pr-4">
                      {current ? (
                        <span className="font-mono text-xs text-foreground">
                          {current.group}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          unassigned (reads as control)
                        </span>
                      )}
                    </td>
                    <td className="py-2">
                      <select
                        aria-label={`Group for ${learner.firstName} ${learner.lastName}`}
                        value={(current?.group as StudyGroupName) ?? ""}
                        disabled={locked || assign.isPending}
                        onChange={(e) =>
                          setGroup(learner.id, e.target.value as StudyGroupName)
                        }
                        className="h-8 rounded-md border border-border bg-background px-2 text-xs focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
                      >
                        <option value="" disabled>
                          Choose…
                        </option>
                        <option value="control">control</option>
                        <option value="adaptive">adaptive</option>
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={confirmLock} onOpenChange={setConfirmLock}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Lock the cohorts?</DialogTitle>
            <DialogDescription>
              This cannot be undone. After locking, no learner&apos;s group can be changed —
              which is the guarantee that the two arms were not rewritten partway through the
              study. Anyone still unassigned will be treated as control and cannot be corrected.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmLock(false)}>
              Not yet
            </Button>
            <Button onClick={doLock} disabled={lock.isPending}>
              {lock.isPending ? "Locking…" : "Lock cohorts"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
