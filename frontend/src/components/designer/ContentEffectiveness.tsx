"use client";

import { useCourseEffectiveness, useStruggleLeaderboard } from "@/hooks/use-analytics";
import type { SectionEffectivenessRow } from "@/types/analytics";

/**
 * What learners DID in each section, as opposed to how they felt.
 *
 * The affect heatmap above this answers "how did learners feel here", from a detector the
 * platform is honest about: two states, both well below certainty, on a channel its own code
 * documents as weak on this paginated interface. This panel answers "what did they do" — going
 * back to re-read, revealing an answer, getting a question wrong — which needs no model to
 * interpret and has been logged on every completion since `section_features` was written,
 * without anything reading it.
 *
 * TWO RULES THIS UI FOLLOWS
 *
 * A null rate renders as an em dash, never as 0%. Zero and unknown are different facts, and a
 * dashboard that conflates them tells a designer that help never works in a section where help
 * was simply never offered.
 *
 * A thin sample is labelled rather than hidden. Seeing "2 learners" next to a number is how a
 * designer knows not to act on it; showing nothing at all would leave them wondering whether the
 * page was broken.
 */

/** Renders a rate, or an em dash when it is genuinely unknown. */
function Rate({ value, suffix = "%" }: { value: number | null; suffix?: string }) {
  if (value === null || value === undefined) {
    return (
      <span className="text-muted-foreground" title="No data recorded for this yet">
        —
      </span>
    );
  }
  return (
    <span className="tabular-nums">
      {value}
      {suffix}
    </span>
  );
}

function intensity(value: number | null): string {
  if (value === null) return "";
  if (value >= 60) return "bg-red-50 text-red-800 dark:bg-red-900/20 dark:text-red-300";
  if (value >= 30) return "bg-amber-50 text-amber-800 dark:bg-amber-900/20 dark:text-amber-300";
  return "";
}

export function ContentEffectiveness({ courseId }: { courseId: string }) {
  const effectiveness = useCourseEffectiveness(courseId);
  const struggle = useStruggleLeaderboard(courseId);

  const sections = effectiveness.data?.sections ?? [];
  const hardest = struggle.data?.sections ?? [];
  const anyData = sections.some((s) => s.observedLearners > 0);

  if (effectiveness.isPending) {
    return (
      <div className="rounded-lg border border-border bg-surface p-6">
        <div className="h-4 w-40 animate-pulse rounded bg-border" />
        <div className="mt-4 space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-9 animate-pulse rounded bg-border/60" />
          ))}
        </div>
      </div>
    );
  }

  if (effectiveness.isError) {
    return (
      <div className="rounded-lg border border-border bg-surface px-5 py-8 text-center">
        <p className="text-sm text-muted-foreground">Couldn&apos;t load content effectiveness.</p>
        <button
          type="button"
          onClick={() => effectiveness.refetch()}
          className="mt-3 rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <section>
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-foreground">What learners did</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Behaviour rather than inferred emotion: going back to re-read, revealing an answer,
          answering wrongly. No model interprets these, so they hold whether or not the camera
          was on.
        </p>
      </div>

      {!anyData && (
        <div className="rounded-lg border border-dashed border-border p-8 text-center">
          <p className="text-sm font-medium text-foreground">No completions recorded yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            These figures appear once learners start finishing sections. Nothing is estimated
            before then.
          </p>
        </div>
      )}

      {anyData && hardest.length > 0 && (
        <div className="mb-5 rounded-lg border border-border bg-surface p-5">
          <h3 className="text-sm font-semibold text-foreground">Hardest sections</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Ranked on revisits, answer reveals and wrong answers combined, with equal weight.
            Sections with too little data to judge are left out rather than ranked low.
          </p>
          <ol className="mt-3 space-y-1.5">
            {hardest.map((row, index) => (
              <li
                key={row.sectionId}
                className="flex items-center gap-3 rounded border border-border px-3 py-2"
              >
                <span className="w-5 shrink-0 text-xs text-muted-foreground">{index + 1}</span>
                <span className="min-w-0 flex-1 truncate text-sm text-foreground">
                  {row.sectionTitle}
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {row.observedLearners} learner{row.observedLearners === 1 ? "" : "s"}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {anyData && (
        <div className="overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full min-w-[860px] text-sm">
            <caption className="sr-only">
              Per-section learner behaviour and assistance for this course
            </caption>
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th scope="col" className="px-4 py-2.5 font-medium">Section</th>
                <th scope="col" className="px-3 py-2.5 font-medium" title="Learners whose completion was recorded">
                  Learners
                </th>
                <th scope="col" className="px-3 py-2.5 font-medium" title="Share who came back to this section after leaving it">
                  Revisited
                </th>
                <th scope="col" className="px-3 py-2.5 font-medium" title="Share who revealed an answer rather than attempting it">
                  Revealed
                </th>
                <th scope="col" className="px-3 py-2.5 font-medium" title="Share of all quiz attempts here that were wrong">
                  Wrong
                </th>
                <th scope="col" className="px-3 py-2.5 font-medium" title="Seconds per 100 words, so long sections are not penalised">
                  Pace
                </th>
                <th scope="col" className="px-3 py-2.5 font-medium" title="Hints and suggestions delivered in this section">
                  Help
                </th>
                <th scope="col" className="px-3 py-2.5 font-medium" title="Of the offers followed by an answer, the share where that answer was correct. An association, not proof the help caused it.">
                  Then correct
                </th>
              </tr>
            </thead>
            <tbody>
              {sections.map((row) => (
                <Row key={row.sectionId} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {anyData && (
        <p className="mt-3 text-xs text-muted-foreground">
          <strong>Then correct</strong> counts offers that were followed by an answer, and reports
          how often that answer was right. It records that the two happened in that order — not
          that the help caused it. A learner may have solved it despite the hint, or ignored it.
        </p>
      )}
    </section>
  );
}

function Row({ row }: { row: SectionEffectivenessRow }) {
  return (
    <tr className="border-b border-border last:border-0">
      <th scope="row" className="max-w-[240px] truncate px-4 py-2.5 text-left font-normal text-foreground">
        {row.sectionTitle}
      </th>
      <td className="px-3 py-2.5">
        <span className="tabular-nums">{row.observedLearners}</span>
        {row.insufficientData && row.observedLearners > 0 && (
          <span
            className="ml-1.5 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-400"
            title="Too few learners for these figures to mean much"
          >
            thin
          </span>
        )}
      </td>
      <td className={`px-3 py-2.5 ${intensity(row.revisitRate)}`}>
        <Rate value={row.revisitRate} />
      </td>
      <td className={`px-3 py-2.5 ${intensity(row.showAnswerUsedRate)}`}>
        <Rate value={row.showAnswerUsedRate} />
      </td>
      <td className={`px-3 py-2.5 ${intensity(row.quizIncorrectRate)}`}>
        <Rate value={row.quizIncorrectRate} />
      </td>
      <td className="px-3 py-2.5">
        <Rate value={row.timePer100Words} suffix="s" />
      </td>
      <td className="px-3 py-2.5 tabular-nums">{row.assistance.offers}</td>
      <td className="px-3 py-2.5">
        <Rate value={row.assistance.followedByCorrectRate} />
        {row.assistance.outcomesRecorded > 0 && (
          <span className="ml-1 text-[11px] text-muted-foreground">
            of {row.assistance.outcomesRecorded}
          </span>
        )}
      </td>
    </tr>
  );
}
