"use client";

/**
 * useSectionSignals — per-section interaction counters for confusion detection.
 *
 * WHY
 *
 * The deployed behavioural model is structurally blind on this UI. Four of its sixteen features
 * are scroll-based, but the lesson shows ONE SECTION PER PAGE with next/prev navigation, so a
 * learner barely scrolls — measured live at 2 scroll events per 30s window with
 * `P(confused) = 0.008` while deliberately trying to appear confused. Its training corpus was
 * business-software users, who scroll constantly.
 *
 * These counters capture what a struggling learner on a PAGINATED lesson actually does: dwelling,
 * navigating backwards, revealing an answer, retrying a quiz.
 *
 * WHY THE CLIENT COUNTS
 *
 * The backend cannot derive these at completion time. `research_logger.emit` publishes to a Redis
 * stream that a background worker later drains into Postgres, so a section's events are not yet
 * queryable when it is completed — and are lost entirely if Redis is down. The page already holds
 * this state, so it rides along in the completion request body instead.
 *
 * These are logged for future model training and do NOT affect what the learner sees.
 */

import { useCallback, useRef } from "react";

export interface SectionSignals {
  timeOnSectionS: number;
  viewCount: number;
  backNavCount: number;
  showAnswerUsed: boolean;
  quizAttemptCount: number;
  quizIncorrectCount: number;
  quizResponseTimeMsMean: number;
  exerciseAttemptCount: number;
  adaptationDeliveredCount: number;
  adaptationDismissedCount: number;
}

interface Counters {
  enteredAtMs: number | null;
  accumulatedMs: number;
  viewCount: number;
  backNavCount: number;
  showAnswerUsed: boolean;
  quizAttemptCount: number;
  quizIncorrectCount: number;
  quizResponseTimes: number[];
  exerciseAttemptCount: number;
  adaptationDeliveredCount: number;
  adaptationDismissedCount: number;
}

const empty = (): Counters => ({
  enteredAtMs: null,
  accumulatedMs: 0,
  viewCount: 0,
  backNavCount: 0,
  showAnswerUsed: false,
  quizAttemptCount: 0,
  quizIncorrectCount: 0,
  quizResponseTimes: [],
  exerciseAttemptCount: 0,
  adaptationDeliveredCount: 0,
  adaptationDismissedCount: 0,
});

export function useSectionSignals() {
  // Refs, not state: these change on every interaction and must never trigger a re-render of the
  // lesson. Keyed by section id so revisiting a section accumulates rather than restarting.
  const bySection = useRef<Map<string, Counters>>(new Map());
  const currentId = useRef<string | null>(null);

  const counters = useCallback((sectionId: string): Counters => {
    let c = bySection.current.get(sectionId);
    if (!c) {
      c = empty();
      bySection.current.set(sectionId, c);
    }
    return c;
  }, []);

  /** Dwell so far, including the open interval if the learner is still on the section. */
  const elapsedMs = useCallback((c: Counters): number => {
    const open = c.enteredAtMs === null ? 0 : Math.max(0, Date.now() - c.enteredAtMs);
    return c.accumulatedMs + open;
  }, []);

  /** Learner is now looking at `sectionId`. Closes the previous section's dwell interval. */
  const enterSection = useCallback(
    (sectionId: string | undefined) => {
      const prev = currentId.current;
      if (prev && prev !== sectionId) {
        const p = counters(prev);
        if (p.enteredAtMs !== null) {
          p.accumulatedMs += Math.max(0, Date.now() - p.enteredAtMs);
          p.enteredAtMs = null;
        }
      }
      if (!sectionId) {
        currentId.current = null;
        return;
      }
      if (prev !== sectionId) {
        const c = counters(sectionId);
        c.viewCount += 1;
        c.enteredAtMs = Date.now();
        currentId.current = sectionId;
      }
    },
    [counters],
  );

  /** Learner navigated BACKWARDS — the paginated equivalent of scrolling back to re-read. */
  const recordBackNav = useCallback(
    (fromSectionId: string | undefined) => {
      if (!fromSectionId) return;
      counters(fromSectionId).backNavCount += 1;
    },
    [counters],
  );

  /** Learner revealed an exercise answer — giving up, and the strongest signal available. */
  const recordShowAnswer = useCallback(
    (sectionId: string | undefined) => {
      if (!sectionId) return;
      counters(sectionId).showAnswerUsed = true;
    },
    [counters],
  );

  const recordQuizAttempt = useCallback(
    (sectionId: string | undefined, isCorrect: boolean, responseTimeMs?: number) => {
      if (!sectionId) return;
      const c = counters(sectionId);
      c.quizAttemptCount += 1;
      if (!isCorrect) c.quizIncorrectCount += 1;
      if (typeof responseTimeMs === "number" && responseTimeMs >= 0) {
        c.quizResponseTimes.push(responseTimeMs);
      }
    },
    [counters],
  );

  const recordExerciseAttempt = useCallback(
    (sectionId: string | undefined) => {
      if (!sectionId) return;
      counters(sectionId).exerciseAttemptCount += 1;
    },
    [counters],
  );

  const recordAdaptation = useCallback(
    (sectionId: string | undefined, dismissed: boolean) => {
      if (!sectionId) return;
      const c = counters(sectionId);
      c.adaptationDeliveredCount += 1;
      if (dismissed) c.adaptationDismissedCount += 1;
    },
    [counters],
  );

  /** Snapshot for the completion request. Does NOT reset — a section can be completed twice. */
  const snapshot = useCallback(
    (sectionId: string | undefined): SectionSignals | undefined => {
      if (!sectionId) return undefined;
      const c = bySection.current.get(sectionId);
      if (!c) return undefined;
      const times = c.quizResponseTimes;
      return {
        timeOnSectionS: Math.round(elapsedMs(c) / 100) / 10,
        viewCount: c.viewCount,
        backNavCount: c.backNavCount,
        showAnswerUsed: c.showAnswerUsed,
        quizAttemptCount: c.quizAttemptCount,
        quizIncorrectCount: c.quizIncorrectCount,
        quizResponseTimeMsMean:
          times.length > 0
            ? Math.round((times.reduce((a, b) => a + b, 0) / times.length) * 10) / 10
            : 0,
        exerciseAttemptCount: c.exerciseAttemptCount,
        adaptationDeliveredCount: c.adaptationDeliveredCount,
        adaptationDismissedCount: c.adaptationDismissedCount,
      };
    },
    [elapsedMs],
  );

  return {
    enterSection,
    recordBackNav,
    recordShowAnswer,
    recordQuizAttempt,
    recordExerciseAttempt,
    recordAdaptation,
    snapshot,
  };
}
