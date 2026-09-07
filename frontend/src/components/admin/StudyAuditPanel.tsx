"use client";

import { CheckCircle2, XCircle } from "lucide-react";

import { useStudyAudit } from "@/hooks/use-study";

/**
 * Research-integrity checks over the A/B allocation (FR50).
 *
 * The A/B page reported allocation and nothing about whether that allocation is sound. The check
 * that matters is contamination — a control-group learner who received an adaptation — because
 * nothing in the schema prevents it: the gate is application logic, and Section 4.5 of the paper
 * records that gate defects go unnoticed precisely until something reports on them.
 *
 * Each check reports its own verdict rather than rolling up into one. "The study is fine" is not
 * actionable, and these fail for different reasons needing different responses.
 */
export function StudyAuditPanel() {
  const { data, isPending, isError } = useStudyAudit();
  const checks = data ?? [];
  const failing = checks.filter((c) => !c.passed);

  return (
    <section className="mt-8 rounded-lg border border-border bg-surface p-6">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-semibold text-foreground">Research integrity</h2>
        {checks.length > 0 && (
          <span
            className={
              failing.length === 0
                ? "text-xs font-medium text-success"
                : "text-xs font-medium text-destructive"
            }
          >
            {failing.length === 0
              ? "All checks pass"
              : `${failing.length} of ${checks.length} failing`}
          </span>
        )}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        Run against the live data every time this page loads.
      </p>

      {isPending ? (
        <p className="mt-4 text-sm text-muted-foreground">Running checks…</p>
      ) : isError ? (
        <p className="mt-4 text-sm text-muted-foreground">Could not run the checks.</p>
      ) : (
        <ul className="mt-4 space-y-3">
          {checks.map((check) => (
            <li key={check.id} className="flex gap-3">
              {check.passed ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 translate-y-0.5 text-success" />
              ) : (
                <XCircle className="h-4 w-4 shrink-0 translate-y-0.5 text-destructive" />
              )}
              <div>
                <p className="text-sm font-medium text-foreground">
                  {check.label}
                  {check.count > 0 && (
                    <span
                      className={
                        check.passed
                          ? "ml-2 text-xs font-normal text-muted-foreground"
                          : "ml-2 text-xs font-normal text-destructive"
                      }
                    >
                      {/* How bad, not only that it happened. */}
                      {check.count}
                    </span>
                  )}
                </p>
                <p className="text-xs text-muted-foreground">{check.detail}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
