"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/cn";
import { useAdaptationStore } from "@/stores/adaptation-store";
import type { Adaptation } from "@/stores/adaptation-store";
import type { AdaptationAction } from "@/types/ws-messages";

/**
 * AdaptationProbe — "Did that help?", asked about ONE specific intervention.
 *
 * WHY THIS EXISTS
 *
 * Nothing else in the system can say whether an intervention helped. `self_report` fires on
 * section completion, references no delivery, and arrives after the learner has left the
 * material. `adaptation_interaction` records dismissal, which is an action and not an appraisal —
 * a learner who closes a hint may well have read and used it. And the affect detector's own later
 * reading is the instrument being evaluated, so it cannot also be the verdict on itself.
 *
 * This is the only signal that carries a learner's judgement of a named intervention, joined by
 * the server-issued `adaptation_id`.
 *
 * WHY IT WAITS
 *
 * Asking immediately would measure the learner's reaction to being interrupted rather than to the
 * help. `PROBE_DELAY_MS` gives them time to read the hint and act on it before being asked. The
 * delay is measured from delivery and reported as `shown_after_ms`, so an answer given after ten
 * seconds is distinguishable in analysis from one given after two minutes.
 *
 * WHY THREE OPTIONS AND NOT A SCALE
 *
 * A rating scale invites deliberation, and a probe that costs thought changes the state it is
 * trying to measure. Three one-tap answers keep the cost near zero. `Not sure` exists so that
 * genuine uncertainty is recorded as an answer instead of being forced into a pole or into
 * silence — and closing the probe stays distinct from all three, because declining to appraise is
 * not a negative appraisal.
 *
 * WHAT IT MUST NOT DO
 *
 * It must never block the lesson. It is an inline bar, not a modal, with no backdrop and no
 * deadline, matching `SelfReportBar`'s "Never Block Learning" rule.
 */

/** Time from delivery until the probe appears. Long enough to read and act on the hint. */
export const PROBE_DELAY_MS = 30_000;

/**
 * Interventions worth probing: the ones that put CONTENT in front of the learner.
 *
 * `skip_ahead` is excluded — "did that help?" after a page advance asks about navigation, not
 * about help, and would dilute the measure with a different question. `suggest_break` is excluded
 * for the same reason: it is answered by whether the learner came back.
 */
const PROBEABLE: ReadonlySet<AdaptationAction> = new Set<AdaptationAction>([
  "show_hint",
  "show_alternative",
  "show_breakdown",
  "show_encouragement",
  "simplify",
  "increase_difficulty",
]);

export type ProbeResponse = "helped" | "did_not_help" | "unsure";

const OPTIONS: { value: ProbeResponse; label: string }[] = [
  { value: "helped", label: "Yes, that helped" },
  { value: "did_not_help", label: "Not really" },
  { value: "unsure", label: "Not sure" },
];

/** The most recent probeable adaptation, or null. Exported for testing the selection rule. */
export function probeTarget(queue: readonly Adaptation[]): Adaptation | null {
  for (let i = queue.length - 1; i >= 0; i -= 1) {
    if (PROBEABLE.has(queue[i].action)) return queue[i];
  }
  return null;
}

export function AdaptationProbe({
  onRespond,
  delayMs = PROBE_DELAY_MS,
}: {
  onRespond?: (payload: {
    adaptation_id: string;
    action: AdaptationAction;
    response: ProbeResponse | null;
    dismissed: boolean;
    shown_after_ms: number;
  }) => void;
  /** Overridable so tests need not wait 30 real seconds. */
  delayMs?: number;
}) {
  const queue = useAdaptationStore((s) => s.adaptationQueue);
  const target = useMemo(() => probeTarget(queue), [queue]);

  const [dueId, setDueId] = useState<string | null>(null);
  // Ids already answered or declined. A learner is asked about a given intervention ONCE:
  // re-asking would train them to dismiss the probe reflexively, and every later answer would
  // be about the annoyance rather than the help.
  const answered = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!target || answered.current.has(target.id)) return;

    const elapsed = Date.now() - target.receivedAt;
    const remaining = Math.max(0, delayMs - elapsed);
    const timer = setTimeout(() => setDueId(target.id), remaining);
    return () => clearTimeout(timer);
  }, [target, delayMs]);

  if (!target || dueId !== target.id || answered.current.has(target.id)) return null;

  const close = (response: ProbeResponse | null) => {
    answered.current.add(target.id);
    setDueId(null);
    onRespond?.({
      adaptation_id: target.id,
      action: target.action,
      response,
      dismissed: response === null,
      shown_after_ms: Date.now() - target.receivedAt,
    });
  };

  return (
    <div
      role="group"
      aria-label="Was that suggestion helpful?"
      className={cn(
        "mt-4 flex flex-wrap items-center gap-2 rounded-lg border border-border",
        "bg-muted/40 px-4 py-3 text-sm",
      )}
    >
      <span className="mr-1 text-foreground">Did that help?</span>
      {OPTIONS.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => close(o.value)}
          className={cn(
            "rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium",
            "text-foreground transition-colors hover:bg-muted",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          )}
        >
          {o.label}
        </button>
      ))}
      <button
        type="button"
        onClick={() => close(null)}
        aria-label="Dismiss this question"
        className={cn(
          "ml-auto rounded px-2 py-1 text-xs text-muted-foreground underline-offset-2",
          "hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        )}
      >
        Skip
      </button>
    </div>
  );
}
