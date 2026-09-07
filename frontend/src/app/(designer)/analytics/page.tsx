"use client";

import { CourseRow } from "@/components/designer/CourseRow";
import { CourseRowSkeleton } from "@/components/designer/CourseRowSkeleton";
import { useCourses } from "@/hooks/use-courses";

/**
 * Analytics landing — pick a course.
 *
 * This page previously rendered a hardcoded affect-colour legend above a permanent
 * "No affect data yet" empty state and called no API at all. It said the same thing whether the
 * deployment had zero sessions or thousands, and it is where every designer LANDS after signing
 * in, so the first screen of the designer experience was one that could not respond to data.
 *
 * The real per-course analytics already existed one route down at `/analytics/[courseId]` —
 * heatmap, effectiveness, section drill-down — reachable only by clicking a row on the dashboard.
 * So this is now the index that was missing rather than a second copy of the dashboard.
 *
 * WHICH COURSES APPEAR
 *
 * Only those whose analytics this designer may actually open: their own, plus seeded/system
 * content, which is shared and is what the pilot runs on. Listing another designer's course here
 * would render a row whose destination answers 403 — the same "buttons that lie" problem the
 * course editor solved by gating its actions on `canEdit`.
 */
export default function AnalyticsIndexPage() {
  const coursesQuery = useCourses({ pageSize: 50 });

  const viewable = (coursesQuery.data?.items ?? []).filter(
    (c) => c.canEdit === true || c.createdBy == null
  );

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Course Analytics</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Choose a course to see its affect heatmap, content effectiveness and section detail.
        </p>
      </div>

      {coursesQuery.isError ? (
        <div className="rounded-lg border border-border bg-surface px-5 py-12 text-center">
          <p className="text-sm font-medium text-foreground">Couldn&apos;t load your courses</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            {(coursesQuery.error as Error)?.message ?? "Something went wrong."}
          </p>
          <button
            type="button"
            onClick={() => coursesQuery.refetch()}
            className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Try again
          </button>
        </div>
      ) : coursesQuery.isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <CourseRowSkeleton key={i} />
          ))}
        </div>
      ) : viewable.length === 0 ? (
        <div className="rounded-lg border border-border bg-surface px-5 py-12 text-center">
          <p className="text-sm font-medium text-foreground">No courses to analyse yet</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            Analytics are per course. Create one under Courses, and its affect data will appear
            here once learners have completed sections.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {viewable.map((course) => (
            <CourseRow key={course.id} course={course} />
          ))}
        </div>
      )}
    </div>
  );
}
