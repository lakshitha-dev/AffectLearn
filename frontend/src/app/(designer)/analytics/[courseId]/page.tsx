"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

/**
 * Per-course affect-heatmap route — the Story 7.2 click-through target.
 *
 * ROUTING DECISION (documented for Story 7.3): the agreed per-course analytics
 * URL is `(designer)/analytics/[courseId]` → `/analytics/<courseId>`. The flat
 * `/analytics` stub remains the section index. Story 7.3 fills in the real
 * affect heatmap grid HERE; this story ships only a placeholder that resolves
 * cleanly inside the designer layout (never a 404) and reads `courseId`.
 */
export default function CourseAnalyticsPlaceholderPage() {
  const params = useParams<{ courseId: string }>();
  const courseId = params?.courseId;

  return (
    <div>
      <div className="mb-8">
        <Link
          href="/dashboard"
          className="text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          ← Back to dashboard
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-foreground">Affect Heatmap</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Per-section emotional analytics for this course
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface px-5 py-16 text-center">
        <p className="text-sm font-medium text-foreground">
          Affect heatmap coming in Story 7.3
        </p>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          The per-section engaged / confused / bored / frustrated grid for course{" "}
          <code className="rounded bg-background/60 px-1.5 py-0.5 text-xs">
            {courseId}
          </code>{" "}
          will render here once Story 7.3 is implemented.
        </p>
      </div>
    </div>
  );
}
