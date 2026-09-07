"use client";

import { useSectionQuestions } from "@/hooks/use-analytics";

/**
 * Item analysis for a section's quiz questions.
 *
 * The endpoint, the typed hook (`useSectionQuestions`) and the response types all existed and
 * nothing rendered any of it — the hook was imported by nothing. A designer could see that a
 * section caused confusion without being able to see WHICH question inside it did, which is the
 * difference between "rewrite this section" and "rewrite this one item".
 *
 * `facility` vs `firstAttemptFacility` is the distinction worth surfacing: overall facility
 * counts every attempt, so it is inflated by learners who retried after feedback. The
 * first-attempt figure is the fairer measure of whether the material taught the thing, and that
 * is the one this table leads with.
 */
export function QuestionAnalysis({ sectionId }: { sectionId: string }) {
  const { data, isPending, isError } = useSectionQuestions(sectionId);

  const questions = data?.questions ?? [];

  const pct = (value: number | null) =>
    value == null ? "—" : `${Math.round(value * 100)}%`;

  return (
    <section className="rounded-lg border border-border bg-surface p-5">
      <h2 className="font-semibold text-foreground">Question difficulty</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        How each quiz item in this section actually performed.
      </p>

      {isPending ? (
        <p className="mt-4 text-sm text-muted-foreground">Loading item analysis…</p>
      ) : isError ? (
        <p className="mt-4 text-sm text-muted-foreground">
          Could not load the item analysis.
        </p>
      ) : questions.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          No quiz questions in this section have been attempted yet.
        </p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="py-2 pr-4 font-medium text-muted-foreground">Question</th>
                <th className="py-2 pr-4 font-medium text-muted-foreground">First try</th>
                <th className="py-2 pr-4 font-medium text-muted-foreground">Overall</th>
                <th className="py-2 pr-4 font-medium text-muted-foreground">Attempts</th>
                <th className="py-2 pr-4 font-medium text-muted-foreground">Learners</th>
                <th className="py-2 font-medium text-muted-foreground">With help shown</th>
              </tr>
            </thead>
            <tbody>
              {questions.map((q) => (
                <tr key={q.blockId} className="border-b border-border/60 align-top">
                  <td className="py-2 pr-4 text-foreground">
                    {q.question ?? <span className="text-muted-foreground">Untitled item</span>}
                    {/*
                      Sample size is stated rather than hidden. A question answered twice can
                      look like the hardest item in the course by accident, and a designer
                      rewriting it on that basis would be acting on noise.
                    */}
                    {q.insufficientData && (
                      <span className="ml-2 rounded-full bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning">
                        Too few attempts
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-4 text-foreground">{pct(q.firstAttemptFacility)}</td>
                  <td className="py-2 pr-4 text-muted-foreground">{pct(q.facility)}</td>
                  <td className="py-2 pr-4 text-muted-foreground">{q.attempts}</td>
                  <td className="py-2 pr-4 text-muted-foreground">{q.learners}</td>
                  <td className="py-2 text-muted-foreground">{q.attemptsWithHelpOnScreen}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <p className="mt-3 text-xs text-muted-foreground">
            <strong className="text-foreground">First try</strong> is the share of learners who
            got it right on their first attempt — the fairer measure of whether the material
            taught it. <strong className="text-foreground">Overall</strong> counts every attempt,
            so it is raised by learners who retried after seeing feedback.
          </p>
        </div>
      )}
    </section>
  );
}
