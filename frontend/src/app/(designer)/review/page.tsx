"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";

/**
 * Expert review of pedagogical decisions.
 *
 * The agent's reported quality is Cohen's kappa 0.79 against the rule policy it was TRAINED on.
 * That is fidelity: an agent faithfully reproducing a bad policy scores identically. Nobody has
 * asked a teacher whether the decisions are any good. This is where they do.
 *
 * THREE THINGS THIS SCREEN DELIBERATELY DOES NOT SHOW
 *
 * The outcome. Knowing the learner went on to answer correctly turns "was this a good decision"
 * into "did it happen to work", and a reviewer told the outcome cannot un-know it.
 *
 * Other reviewers' ratings, before this one is submitted. Seeing another score first makes this
 * one partly a measure of that one, and the agreement statistic then flatters itself.
 *
 * The learner. Judging pedagogy needs the situation, not the person.
 */

interface Decision {
  assistanceEventId: string;
  actionType: string;
  urgency: string | null;
  hintText: string | null;
  rationale: string | null;
  affectState: string | null;
  affectSource: string | null;
  affectConfidence: number | null;
  cycleNumber: number;
  generated: boolean;
  fallbackReason: string | null;
  reviewedCount: number;
  sampleSize: number;
}

interface Rubric {
  dimensions: string[];
  minRating: number;
  maxRating: number;
}

interface Summary {
  sampleSize: number;
  reviewableTotal: number;
  reviewsSubmitted: number;
  reviewerCount: number;
  decisionsWithAnyReview: number;
  dimensionMeans: Record<string, number | null>;
  wouldMakeSameCallRate: number | null;
  pairwiseAgreement: {
    reviewerA: string;
    reviewerB: string;
    sharedDecisions: number;
    rawAgreement: number;
    cohensKappa: number | null;
  }[];
}

const DIMENSION_HELP: Record<string, string> = {
  appropriateness: "Given the learner's state, was intervening the right call at all?",
  timing: "Was this the right moment — not before they had struggled, not long after giving up?",
  quality: "Is the content itself accurate and pitched right for the material?",
  restraint: "Does it help them reason, rather than handing over the answer?",
};

export default function DecisionReviewPage() {
  const queryClient = useQueryClient();

  const rubric = useQuery<Rubric>({
    queryKey: ["reviews", "rubric"],
    queryFn: () => apiFetch<Rubric>("/reviews/rubric"),
  });
  const decision = useQuery<Decision | null>({
    queryKey: ["reviews", "next"],
    queryFn: () => apiFetch<Decision | null>("/reviews/next"),
  });
  const summary = useQuery<Summary>({
    queryKey: ["reviews", "summary"],
    queryFn: () => apiFetch<Summary>("/reviews/summary"),
  });

  const [ratings, setRatings] = useState<Record<string, number>>({});
  const [sameCall, setSameCall] = useState<boolean | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = useMutation({
    mutationFn: (body: unknown) =>
      apiFetch("/reviews", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      setRatings({});
      setSameCall(null);
      setComment("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["reviews"] });
    },
    onError: () => setError("Could not save that rating. Please try again."),
  });

  const dimensions = rubric.data?.dimensions ?? [];
  const complete =
    dimensions.length > 0 &&
    dimensions.every((d) => ratings[d] !== undefined) &&
    sameCall !== null;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">Decision review</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Rate the calls the system made. You are judging the decision as it was made — you are
          not shown what the learner did next, because that would change the question from
          &ldquo;was this right?&rdquo; to &ldquo;did it work?&rdquo;
        </p>
      </div>

      {summary.data && <Progress summary={summary.data} />}

      {decision.isPending && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </p>
      )}

      {!decision.isPending && !decision.data && (
        <div className="rounded-lg border border-dashed border-border p-10 text-center">
          <p className="text-sm font-medium text-foreground">
            {summary.data && summary.data.reviewableTotal === 0
              ? "No decisions to review yet"
              : "You have rated every decision in the sample"}
          </p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {summary.data && summary.data.reviewableTotal === 0
              ? "Decisions appear here once the system has delivered help to a learner. Before a study has run, that is expected to be very few."
              : "Thank you. Agreement figures update as other reviewers finish."}
          </p>
        </div>
      )}

      {decision.data && (
        <ReviewForm
          decision={decision.data}
          dimensions={dimensions}
          ratings={ratings}
          setRatings={setRatings}
          sameCall={sameCall}
          setSameCall={setSameCall}
          comment={comment}
          setComment={setComment}
          error={error}
          complete={complete}
          pending={submit.isPending}
          onSubmit={(decisionId) =>
            submit.mutate({
              assistanceEventId: decisionId,
              ratings,
              wouldMakeSameCall: sameCall,
              comment: comment.trim() || null,
            })
          }
        />
      )}

      {summary.data && summary.data.reviewsSubmitted > 0 && (
        <Agreement summary={summary.data} />
      )}
    </div>
  );
}

/** Extracted so the decision is a non-null prop rather than a narrowed closure capture. */
function ReviewForm({
  decision,
  dimensions,
  ratings,
  setRatings,
  sameCall,
  setSameCall,
  comment,
  setComment,
  error,
  complete,
  pending,
  onSubmit,
}: {
  decision: Decision;
  dimensions: string[];
  ratings: Record<string, number>;
  setRatings: React.Dispatch<React.SetStateAction<Record<string, number>>>;
  sameCall: boolean | null;
  setSameCall: (v: boolean) => void;
  comment: string;
  setComment: (v: string) => void;
  error: string | null;
  complete: boolean;
  pending: boolean;
  onSubmit: (decisionId: string) => void;
}) {
  return (
        <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
          <DecisionCard decision={decision} />

          <div className="rounded-lg border border-border bg-surface p-5">
            <h2 className="mb-1 text-sm font-semibold text-foreground">Your rating</h2>
            <p className="mb-4 text-xs text-muted-foreground">
              1 = poor, 5 = excellent.
            </p>

            <div className="space-y-4">
              {dimensions.map((dimension) => (
                <fieldset key={dimension}>
                  <legend className="text-xs font-medium capitalize text-foreground">
                    {dimension}
                  </legend>
                  <p className="mb-1.5 text-[11px] text-muted-foreground">
                    {DIMENSION_HELP[dimension] ?? ""}
                  </p>
                  <div className="flex gap-1.5">
                    {[1, 2, 3, 4, 5].map((value) => (
                      <button
                        key={value}
                        type="button"
                        aria-label={`${dimension} ${value}`}
                        aria-pressed={ratings[dimension] === value}
                        onClick={() => setRatings((r) => ({ ...r, [dimension]: value }))}
                        className={`h-8 w-8 rounded border text-xs font-medium ${
                          ratings[dimension] === value
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-border text-foreground"
                        }`}
                      >
                        {value}
                      </button>
                    ))}
                  </div>
                </fieldset>
              ))}

              <fieldset className="border-t border-border pt-4">
                <legend className="text-xs font-medium text-foreground">
                  Would you have made the same call?
                </legend>
                <p className="mb-1.5 text-[11px] text-muted-foreground">
                  The headline judgement, and the one agreement between reviewers is measured on.
                </p>
                <div className="flex gap-2">
                  {[
                    { label: "Yes", value: true },
                    { label: "No", value: false },
                  ].map((option) => (
                    <button
                      key={option.label}
                      type="button"
                      aria-pressed={sameCall === option.value}
                      onClick={() => setSameCall(option.value)}
                      className={`rounded border px-3 py-1.5 text-sm font-medium ${
                        sameCall === option.value
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-border text-foreground"
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>

              <label className="block text-xs font-medium text-foreground">
                Comment <span className="font-normal text-muted-foreground">(optional)</span>
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  rows={3}
                  placeholder="What would you have done instead?"
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                />
              </label>

              {error && (
                <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800/40 dark:bg-red-900/10 dark:text-red-400">
                  {error}
                </p>
              )}

              <button
                type="button"
                disabled={!complete || pending}
                onClick={() => onSubmit(decision.assistanceEventId)}
                className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                {pending ? "Saving…" : "Submit and show next"}
              </button>
            </div>
          </div>
        </div>
  );
}

function DecisionCard({ decision }: { decision: Decision }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded bg-slate-100 px-2 py-0.5 font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300">
          {decision.actionType}
        </span>
        {decision.urgency && (
          <span className="text-muted-foreground">urgency: {decision.urgency}</span>
        )}
        <span
          className={`rounded px-2 py-0.5 font-medium ${
            decision.generated
              ? "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
              : "bg-amber-50 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300"
          }`}
          title={
            decision.generated
              ? "Written by the language model"
              : "Written by the deterministic rule fallback — the model was unavailable"
          }
        >
          {decision.generated ? "model-written" : "rule fallback"}
        </span>
      </div>

      <section className="mb-4">
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          The situation
        </h3>
        <p className="text-sm text-foreground">
          The system read the learner as{" "}
          <strong>{decision.affectState ?? "unknown"}</strong>
          {decision.affectConfidence !== null && (
            <> at {Math.round(decision.affectConfidence * 100)}% confidence</>
          )}
          {decision.affectSource && (
            <> from the {decision.affectSource.replace(/_/g, " ")} channel</>
          )}
          , on cycle {decision.cycleNumber}.
        </p>
      </section>

      {decision.rationale && (
        <section className="mb-4">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Its stated reason
          </h3>
          <p className="rounded border border-border bg-background px-3 py-2 text-sm italic text-muted-foreground">
            {decision.rationale}
          </p>
        </section>
      )}

      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          What the learner was shown
        </h3>
        <p className="rounded border border-border bg-background px-3 py-2.5 text-sm text-foreground">
          {decision.hintText}
        </p>
      </section>
    </div>
  );
}

function Progress({ summary }: { summary: Summary }) {
  return (
    <p className="mb-5 text-xs text-muted-foreground">
      {summary.reviewsSubmitted} rating{summary.reviewsSubmitted === 1 ? "" : "s"} from{" "}
      {summary.reviewerCount} reviewer{summary.reviewerCount === 1 ? "" : "s"} across{" "}
      {summary.decisionsWithAnyReview} of {summary.sampleSize} sampled decisions
      {summary.reviewableTotal > summary.sampleSize && (
        <> ({summary.reviewableTotal} exist in total)</>
      )}
      .
    </p>
  );
}

function Agreement({ summary }: { summary: Summary }) {
  return (
    <section className="mt-8">
      <h2 className="text-sm font-semibold text-foreground">Agreement so far</h2>
      <p className="mt-0.5 max-w-2xl text-xs text-muted-foreground">
        Reported per pair rather than as one number: with a handful of reviewers, a pooled figure
        hides that one of them disagrees with everyone — which usually means the rubric is
        ambiguous rather than that the rater is wrong.
      </p>

      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Object.entries(summary.dimensionMeans).map(([dimension, mean]) => (
          <div key={dimension} className="rounded-lg border border-border bg-surface p-3">
            <div className="text-xs capitalize text-muted-foreground">{dimension}</div>
            <div className="mt-1 text-xl font-semibold tabular-nums text-foreground">
              {mean === null ? "—" : mean}
            </div>
          </div>
        ))}
      </div>

      {summary.pairwiseAgreement.length > 0 && (
        <div className="mt-4 overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full min-w-[520px] text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th scope="col" className="px-4 py-2.5 font-medium">Pair</th>
                <th scope="col" className="px-3 py-2.5 font-medium">Shared</th>
                <th scope="col" className="px-3 py-2.5 font-medium">Raw agreement</th>
                <th
                  scope="col"
                  className="px-3 py-2.5 font-medium"
                  title="Agreement corrected for what chance alone would produce"
                >
                  Cohen&apos;s κ
                </th>
              </tr>
            </thead>
            <tbody>
              {summary.pairwiseAgreement.map((pair) => (
                <tr
                  key={`${pair.reviewerA}-${pair.reviewerB}`}
                  className="border-b border-border last:border-0"
                >
                  <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                    {pair.reviewerA.slice(0, 8)} / {pair.reviewerB.slice(0, 8)}
                  </td>
                  <td className="px-3 py-2.5 tabular-nums">{pair.sharedDecisions}</td>
                  <td className="px-3 py-2.5 tabular-nums">{pair.rawAgreement}%</td>
                  <td className="px-3 py-2.5 tabular-nums">
                    {pair.cohensKappa === null ? (
                      <span
                        className="text-muted-foreground"
                        title="Undefined — one reviewer gave the same answer to everything, so chance agreement is 100% and κ has no denominator. That is a finding, not a zero."
                      >
                        —
                      </span>
                    ) : (
                      pair.cohensKappa
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
