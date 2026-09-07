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
import { usePhaseHistory, useSetPhase, useStudyPhase } from "@/hooks/use-study";

/**
 * The global study phase, its history, and the emergency revert (Story 8.4 / FR46).
 *
 * `POST /admin/study/phase` existed and nothing called it, so the single switch that decides
 * whether ANY learner can receive an intervention could only be thrown with a hand-written HTTP
 * request. Eligibility is exactly `phase_b AND adaptive`, which makes this the most consequential
 * control in the console.
 *
 * The history comes from the `phase_transition` research events rather than a table: `study_phase`
 * is a singleton holding only the current value, so "when did we move to Phase B, and who moved
 * it" was recorded all along and simply had no reader.
 */
export function PhaseControl() {
  const phaseQuery = useStudyPhase();
  const historyQuery = usePhaseHistory();
  const setPhase = useSetPhase();
  const [pendingPhase, setPendingPhase] = useState<string | null>(null);

  const phase = phaseQuery.data?.phase;
  const history = historyQuery.data ?? [];
  const target = phase === "phase_b" ? "phase_a" : "phase_b";
  const isRevert = target === "phase_a";

  async function confirm() {
    if (!pendingPhase) return;
    try {
      await setPhase.mutateAsync({ phase: pendingPhase });
      toast.success(
        pendingPhase === "phase_b"
          ? "Phase B is live. Adaptive-group learners can now receive interventions."
          : "Reverted to Phase A. No learner will receive an intervention."
      );
      setPendingPhase(null);
    } catch {
      toast.error("Could not change the phase.");
    }
  }

  return (
    <section className="mt-8 rounded-lg border border-border bg-surface p-6">
      <h2 className="font-semibold text-foreground">Study phase</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Interventions require <span className="font-mono text-xs">phase_b</span> and the{" "}
        <span className="font-mono text-xs">adaptive</span> group. In{" "}
        <span className="font-mono text-xs">phase_a</span> everyone is logged and nobody is
        adapted.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-4">
        <span
          className={
            phase === "phase_b"
              ? "rounded-full bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
              : "rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300"
          }
        >
          {phaseQuery.isPending ? "Loading…" : phase ?? "unknown"}
        </span>

        {phaseQuery.data?.transitionedAt && (
          <span className="text-xs text-muted-foreground">
            Since {new Date(phaseQuery.data.transitionedAt).toLocaleString()}
          </span>
        )}

        <Button
          size="sm"
          variant={isRevert ? "outline" : "default"}
          disabled={phaseQuery.isPending || setPhase.isPending}
          onClick={() => setPendingPhase(target)}
        >
          {isRevert ? "Revert to Phase A" : "Start Phase B"}
        </Button>
      </div>

      {history.length > 0 && (
        <div className="mt-6">
          <h3 className="text-sm font-medium text-foreground">History</h3>
          <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
            {history.map((entry) => (
              <li key={`${entry.timestamp}-${entry.toPhase}`}>
                <span className="font-mono">{entry.fromPhase}</span> →{" "}
                <span className="font-mono text-foreground">{entry.toPhase}</span>
                {entry.transitionedAt && (
                  <> · {new Date(entry.transitionedAt).toLocaleString()}</>
                )}
                {/* Who threw the switch. A UUID would not answer the question. */}
                {entry.actorName && <> · by {entry.actorName}</>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <Dialog open={pendingPhase !== null} onOpenChange={(open) => !open && setPendingPhase(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {isRevert ? "Revert to Phase A?" : "Start Phase B?"}
            </DialogTitle>
            <DialogDescription>
              {isRevert ? (
                <>
                  Adaptive-group learners will stop receiving interventions immediately. The
                  transition is timestamped, so the data either side of it stays separable — but
                  a study that changes phase twice has two boundaries to account for in the
                  analysis.
                </>
              ) : (
                <>
                  Adaptive-group learners begin receiving interventions; the control group
                  continues to be logged only. The moment of transition is stamped as the clean
                  boundary the dataset is partitioned on, so cycles either side of it are not
                  comparable and must not be pooled.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingPhase(null)}>
              Cancel
            </Button>
            <Button onClick={confirm} disabled={setPhase.isPending}>
              {setPhase.isPending ? "Applying…" : "Confirm"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
