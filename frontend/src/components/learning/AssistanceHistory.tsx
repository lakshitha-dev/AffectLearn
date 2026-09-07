"use client";

import { useQuery } from "@tanstack/react-query";
import { Lightbulb } from "lucide-react";

import { apiFetch } from "@/lib/api-client";

interface AssistanceHistoryItem {
  id: string;
  createdAt: string;
  actionType: string | null;
  hintText: string | null;
  interaction: string | null;
  outcomeIsCorrect: boolean | null;
}

/** Learner-facing wording. The internal action names are not written for people to read. */
const ACTION_LABEL: Record<string, string> = {
  show_hint: "Hint",
  show_alternative: "Another way of looking at it",
  show_breakdown: "Step-by-step breakdown",
  simplify: "Simplified explanation",
  show_encouragement: "Encouragement",
  suggest_break: "Break suggestion",
  increase_difficulty: "A harder version",
  skip_ahead: "Skipped ahead",
};

/**
 * The help this learner has been shown.
 *
 * Every hint the platform delivered was written to `assistance_events`, and the service that reads
 * them back carries the docstring "The read behind a learner-facing hint history" — for a screen
 * that was never built. Learners saw a hint once, in passing, and had no way to find it again.
 *
 * Shows what was on screen and what the learner did with it. It does NOT show the affect
 * inference behind the decision: `architecture.md` lists telling learners their detected state as
 * an anti-pattern, and the endpoint does not return it.
 */
export function AssistanceHistory() {
  const { data, isPending, isError } = useQuery<AssistanceHistoryItem[]>({
    queryKey: ["assistanceHistory"],
    queryFn: () => apiFetch<AssistanceHistoryItem[]>("/learners/me/assistance?limit=50"),
  });

  const items = data ?? [];

  return (
    <section className="rounded-lg border border-border bg-surface p-6">
      <h2 className="font-semibold text-foreground">Help you&apos;ve been given</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Hints and explanations AffectLearn offered while you were studying.
      </p>

      {isPending ? (
        <p className="mt-4 text-sm text-muted-foreground">Loading…</p>
      ) : isError ? (
        <p className="mt-4 text-sm text-muted-foreground">
          Could not load your help history right now.
        </p>
      ) : items.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          Nothing yet. As you work through lessons, any hints you receive will be collected here
          so you can look back at them.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {items.map((item) => (
            <li key={item.id} className="rounded-md border border-border bg-background p-4">
              <div className="flex items-baseline gap-2">
                <Lightbulb className="h-4 w-4 shrink-0 translate-y-0.5 text-muted-foreground" />
                <span className="text-sm font-medium text-foreground">
                  {ACTION_LABEL[item.actionType ?? ""] ?? "Help"}
                </span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {new Date(item.createdAt).toLocaleString()}
                </span>
              </div>

              {item.hintText && (
                <p className="mt-2 whitespace-pre-line text-sm text-muted-foreground">
                  {item.hintText}
                </p>
              )}

              {/*
                `outcomeIsCorrect` is deliberately three-valued: null means there was no next
                attempt, which is not the same as getting it wrong. Rendering null as "wrong"
                would invent a failure the learner never had.
              */}
              {item.outcomeIsCorrect !== null && (
                <p className="mt-2 text-xs text-muted-foreground">
                  {item.outcomeIsCorrect
                    ? "You got the next question right after this."
                    : "The next answer after this one wasn't right — worth another look."}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
