"use client";

import { useLearnerProgress } from "@/hooks/use-progress";

interface ThankYouSummaryProps {
  /** The authenticated learner's id; the achievements summary reads their own progress. */
  learnerId: string | undefined;
}

/**
 * End-of-study "Thank you" screen + learning-achievements summary (Story 6.4).
 *
 * Shown after a successful survey submission. Achievements are sourced from the EXISTING
 * Story 4.6 learner-progress aggregate (`GET /learner-profiles/{id}/progress`) — progress is
 * NOT recomputed here. The screen acknowledges completion warmly ("Accomplished & Capable"
 * goal) and is loading/empty-safe if progress is unavailable. The heading + summary live in an
 * `aria-live` region, mirroring AssessmentResults.tsx.
 */
export function ThankYouSummary({ learnerId }: ThankYouSummaryProps) {
  const { data, isLoading, isError } = useLearnerProgress(learnerId);

  const courses = data?.courses ?? [];
  const totalCompletedSections = courses.reduce(
    (sum, c) => sum + c.completedSections,
    0,
  );
  const totalSections = courses.reduce((sum, c) => sum + c.totalSections, 0);
  const overallPercentage =
    totalSections > 0
      ? Math.round((totalCompletedSections / totalSections) * 100)
      : 0;

  return (
    <div className="max-w-2xl mx-auto px-8 py-12 space-y-8">
      <div
        aria-live="polite"
        className="rounded-xl border border-border bg-surface p-6 text-center space-y-2"
      >
        <h1 className="text-3xl font-semibold text-foreground">Thank you!</h1>
        <p className="text-base text-muted-foreground">
          Your responses help us make AffectLearn better. You finished everything — nicely
          done.
        </p>
      </div>

      <section
        aria-label="Your learning achievements"
        className="rounded-xl border border-border bg-surface p-6 space-y-4"
      >
        <h2 className="text-lg font-semibold text-foreground">
          What you accomplished
        </h2>

        {isLoading ? (
          <p className="text-sm text-muted-foreground" role="status">
            Loading your achievements…
          </p>
        ) : isError || courses.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Your achievements summary isn&apos;t available right now, but your progress is
            saved.
          </p>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-6">
              <Stat
                label="Sections completed"
                value={`${totalCompletedSections} / ${totalSections}`}
              />
              <Stat label="Overall progress" value={`${overallPercentage}%`} />
              {data?.quizzes && (
                <Stat
                  label="Quiz answers correct"
                  value={`${data.quizzes.correct} / ${data.quizzes.answered}`}
                />
              )}
            </div>

            <ul className="space-y-2">
              {courses.map((course) => (
                <li
                  key={course.courseId}
                  className="flex items-center justify-between rounded-lg border border-border px-4 py-3"
                >
                  <span className="text-sm font-medium text-foreground">
                    {course.courseTitle}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {course.completedSections}/{course.totalSections} sections ·{" "}
                    {Math.round(course.percentage)}%
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section
        aria-label="About this study"
        className="rounded-xl border border-border bg-surface p-6 space-y-3 text-sm leading-relaxed"
      >
        <h2 className="text-lg font-semibold text-foreground">About this study</h2>
        <p className="text-muted-foreground">
          Now that you have finished, here is what we were really studying. AffectLearn is
          research into how learners <strong>feel</strong> while they study — moments of
          engagement, boredom, confusion, and mild frustration — and how those feelings show up
          in webcam and mouse/keyboard signals. We were studying those emotions,{" "}
          <strong>not testing you</strong>; there was no score you needed to reach.
        </p>
        <p className="text-muted-foreground">
          To observe a natural range of feelings, the lessons were deliberately varied: some
          sections were meant to feel clear and engaging, some were dense reference material that
          can feel tedious, and a few were intentionally challenging or held ideas that seem to
          contradict each other before they resolve. If parts felt slow, confusing, or hard, that
          was by design and is completely normal — not a reflection of your ability.
        </p>
        <p className="text-muted-foreground">
          No photos or video from your webcam were ever sent or stored — only measurements
          taken from them on your own device, such as eye, mouth and head position.
          Your records are pseudonymised — linked to your study code, not your name — and kept for
          the period stated in the information sheet. You may still withdraw and have your data
          deleted up to the withdrawal deadline; contact the research team with any questions.
        </p>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-2xl font-semibold text-foreground">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
