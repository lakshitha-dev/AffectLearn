"use client";

import { useEffect, useRef } from "react";

/**
 * Send the current section's struggle counters over the socket, every cycle.
 *
 * WHY THIS EXISTS
 *
 * `use-section-signals` has accumulated these counters all along, and they were only ever sent
 * at COMPLETION — in the body of the section-progress request. That is the right place for the
 * training record, and it is useless for intervening: by the time a learner finishes a section,
 * the moment to help them has passed. Worse, a learner who gets stuck and gives up never
 * completes it, so the counters describing the hardest case were the ones never sent.
 *
 * This is the same data on the live path. It is the third detection channel, and the only one
 * that is not a model.
 *
 * WHY IT MATTERS ON THIS PARTICULAR INTERFACE
 *
 * Both trained channels are weak here and the codebase says so. `section_features` records the
 * behavioural model as "structurally blind on this UI" — four of its sixteen features are
 * scroll-based, the reader shows one section per page, and a learner barely scrolls; measured
 * live, two scroll events per window and P(confused) = 0.008 while someone was deliberately
 * trying to appear confused. The facial channel's live scores compressed into a band narrower
 * than the distance to its own threshold.
 *
 * A gate that almost never opens makes the adaptive arm of a study indistinguishable, from the
 * learner's side, from the control arm.
 *
 * WHAT IT SENDS
 *
 * Counts of things the learner did. No text, no answers, no identifiers beyond the section —
 * nothing that is not already recorded at completion.
 */

/** Matches the server's 30s agent cycle, so the channel is evaluated on the same beat. */
const CYCLE_MS = 30_000;

interface SectionSnapshot {
  backNavCount: number;
  showAnswerUsed: boolean;
  quizAttemptCount: number;
  quizIncorrectCount: number;
  timeOnSectionS: number;
}

export function usePerformanceWindow({
  send,
  sectionId,
  snapshot,
  enabled = true,
}: {
  send: (envelope: { type: string; ts: number; data: Record<string, unknown> }) => void;
  sectionId: string | undefined;
  //: Matches `useSectionSignals().snapshot` exactly, including its undefined cases — a section
  //: the learner has not entered has no counters, and inventing zeros for it would report a
  //: calm learner where there is simply no observation.
  snapshot: (sectionId: string | undefined) => SectionSnapshot | undefined;
  enabled?: boolean;
}) {
  const cycle = useRef(0);
  // Held in refs so the interval is created ONCE. Depending on `snapshot` or `sectionId`
  // directly would tear down and recreate the timer on every section change, resetting the
  // cycle counter and re-starting the 30s clock — so a learner moving between sections quickly
  // would never complete a cycle and the channel would never fire.
  const latest = useRef({ send, sectionId, snapshot, enabled });
  latest.current = { send, sectionId, snapshot, enabled };

  useEffect(() => {
    const timer = setInterval(() => {
      const current = latest.current;
      if (!current.enabled || !current.sectionId) return;

      const s = current.snapshot(current.sectionId);
      if (!s) return;
      cycle.current += 1;

      // snake_case on the wire: the WebSocket protocol is snake_case in both directions, a
      // deliberate exception to the REST camelCase rule (see the routes README).
      current.send({
        type: "performance_window",
        ts: Date.now(),
        data: {
          cycle_number: cycle.current,
          section_id: current.sectionId,
          back_nav_count: s.backNavCount,
          show_answer_used: s.showAnswerUsed,
          quiz_attempt_count: s.quizAttemptCount,
          quiz_incorrect_count: s.quizIncorrectCount,
          time_on_section_s: s.timeOnSectionS,
        },
      });
    }, CYCLE_MS);

    return () => clearInterval(timer);
  }, []);
}
