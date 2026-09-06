"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { AffectHeatmapGrid } from "@/components/designer/AffectHeatmapGrid";
import { HeatmapGridSkeleton } from "@/components/designer/HeatmapGridSkeleton";
import { ContentEffectiveness } from "@/components/designer/ContentEffectiveness";
import { useAffectHeatmap } from "@/hooks/use-analytics";

/**
 * Per-course affect-heatmap page (Story 7.3) — the designer "aha moment".
 *
 * ROUTING: the agreed per-course analytics URL is
 * `(designer)/analytics/[courseId]` → `/analytics/<courseId>` (the 7.2 → 7.3
 * click-through). This page replaces the 7.2 placeholder body with the real
 * `role="grid"` heatmap; clicking a row navigates to
 * `/analytics/{courseId}/sections/{sectionId}` (the Story 7.4 detail route,
 * stubbed by this story so the link always resolves).
 *
 * STATES (AC5): `isPending` → skeleton grid (NOT a spinner); fetch error →
 * inline message + Retry; `sections: []` → the exact empty-state copy; data →
 * the heatmap grid.
 */
export default function CourseAffectHeatmapPage() {
  const params = useParams<{ courseId: string }>();
  const courseId = params?.courseId ?? "";

  const heatmapQuery = useAffectHeatmap(courseId);
  const sections = heatmapQuery.data?.sections ?? [];

  return (
    <div>
      <div className="mb-8">
        <Link
          href="/dashboard"
          className="text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          ← Back to dashboard
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-foreground">Course analytics</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          How learners felt, and what they did, section by section
        </p>
      </div>

      {heatmapQuery.isPending ? (
        <HeatmapGridSkeleton />
      ) : heatmapQuery.isError ? (
        <div className="rounded-lg border border-border bg-surface px-5 py-12 text-center">
          <p className="text-sm font-medium text-foreground">
            Couldn&apos;t load the affect heatmap
          </p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            {(heatmapQuery.error as Error)?.message ?? "Something went wrong."}
          </p>
          <button
            type="button"
            onClick={() => heatmapQuery.refetch()}
            className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Retry
          </button>
        </div>
      ) : sections.length === 0 ? (
        <div className="rounded-lg border border-border bg-surface px-5 py-16 text-center">
          <p className="text-sm font-medium text-foreground">No data yet</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            No data yet — learners need to complete sessions before affect data
            appears
          </p>
        </div>
      ) : (
        <AffectHeatmapGrid courseId={courseId} sections={sections} />
      )}

      {/*
        The behavioural evidence, below the affect heatmap and on the same page ON PURPOSE.

        The heatmap reports inferred emotion from a detector the platform is candid about: two
        states, both well below certainty, on a channel its own code documents as structurally
        weak on this paginated reader. This panel reports what learners actually did. Putting
        them side by side is what lets a designer weigh one against the other instead of
        treating the heatmap as the whole picture.
      */}
      <div className="mt-10">
        <ContentEffectiveness courseId={courseId} />
      </div>
    </div>
  );
}
