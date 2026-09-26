"use client";

import { useEffect, useRef } from "react";

/** The server holds help for 45 s after the latest report, so one report every 10 s is plenty. */
export const QUIZ_ACTIVITY_THROTTLE_MS = 10_000;

/** Marks a block whose interaction means "the learner is answering a question". */
export const QUIZ_SELECTOR = "[data-quiz]";

/**
 * Report that the learner is answering a question, so the server holds automatic help meanwhile.
 *
 * Tapping an option, focusing or typing inside any `[data-quiz]` element counts. The attribute has
 * to be on every block a learner answers inside a lesson (`QuizBlock`, `ExerciseBlock`) -- when it
 * was only on the assessment screen's `QuestionCard`, this listener never matched on a lesson page
 * and the server's `quiz_active` hold could not fire there at all.
 */
export function useQuizActivity(
  send: (envelope: { type: "ui_event"; ts: number; data: { event: "quiz_activity" } }) => void,
): void {
  const lastReport = useRef(0);
  const sendRef = useRef(send);
  sendRef.current = send;

  useEffect(() => {
    const onActivity = (e: Event) => {
      const target = e.target as Element | null;
      if (!target?.closest?.(QUIZ_SELECTOR)) return;
      const now = Date.now();
      if (now - lastReport.current < QUIZ_ACTIVITY_THROTTLE_MS) return;
      lastReport.current = now;
      sendRef.current({ type: "ui_event", ts: now, data: { event: "quiz_activity" } });
    };
    document.addEventListener("pointerdown", onActivity, true);
    document.addEventListener("focusin", onActivity, true);
    document.addEventListener("keydown", onActivity, true);
    return () => {
      document.removeEventListener("pointerdown", onActivity, true);
      document.removeEventListener("focusin", onActivity, true);
      document.removeEventListener("keydown", onActivity, true);
    };
  }, []);
}
