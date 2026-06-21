"use client";

import { CourseRow } from "@/components/designer/CourseRow";
import { CourseRowSkeleton } from "@/components/designer/CourseRowSkeleton";
import { StatCard } from "@/components/designer/StatCard";
import { StatCardSkeleton } from "@/components/designer/StatCardSkeleton";
import { useCourseOverview } from "@/hooks/use-analytics";
import { useCourses } from "@/hooks/use-courses";

/**
 * Designer dashboard overview (Story 7.2).
 *
 * AGGREGATION DECISION (documented per Task 4.3): the 7.1 overview contract is
 * PER-COURSE — there is no course-agnostic rollup endpoint. So the 4 top stat
 * cards reflect a SINGLE selected course (the designer's first course, named in
 * the header) and each list row below carries its own per-course overview
 * metrics. We do NOT fabricate a cross-course aggregate the backend never
 * returned.
 *
 * INDICATOR DECISION (Task 3.3 / AC2): the contract supplies `confidence` +
 * `sampleCount`, not a period-over-period trend, so cards surface those as the
 * honest supporting indicator and a "Limited data" badge when `insufficientData`
 * / low confidence — never a fabricated "+x% vs last week".
 */
export default function DesignerDashboardPage() {
  const coursesQuery = useCourses({ pageSize: 50 });
  const courses = coursesQuery.data?.items ?? [];
  const primaryCourse = courses[0];

  const overviewQuery = useCourseOverview(primaryCourse?.id);
  const overview = overviewQuery.data;

  const formatPct = (value: number) => `${Math.round(value)}%`;
  const indicatorFor = () =>
    overview ? `${overview.sampleCount} samples · ${overview.confidence} confidence` : undefined;

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {primaryCourse
            ? `Affect analytics overview · ${primaryCourse.title}`
            : "High-level affect analytics across your courses"}
        </p>
      </div>

      {/* --- Courses fetch error --- */}
      {coursesQuery.isError ? (
        <div className="rounded-lg border border-border bg-surface px-5 py-12 text-center">
          <p className="text-sm font-medium text-foreground">
            Couldn&apos;t load your dashboard
          </p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            {(coursesQuery.error as Error)?.message ?? "Something went wrong."}
          </p>
          <button
            type="button"
            onClick={() => coursesQuery.refetch()}
            className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Retry
          </button>
        </div>
      ) : (
        <>
          {/* --- Stat cards --- */}
          <section
            aria-label="Course metrics"
            className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
          >
            {coursesQuery.isPending ||
            (primaryCourse && overviewQuery.isPending) ? (
              <>
                <StatCardSkeleton />
                <StatCardSkeleton />
                <StatCardSkeleton />
                <StatCardSkeleton />
              </>
            ) : !primaryCourse ? null : overviewQuery.isError || !overview ? (
              <div className="col-span-full rounded-xl border border-border bg-surface p-6 text-sm text-muted-foreground shadow-sm">
                Metrics are unavailable right now.{" "}
                <button
                  type="button"
                  onClick={() => overviewQuery.refetch()}
                  className="font-medium text-primary hover:underline"
                >
                  Retry
                </button>
              </div>
            ) : (
              <>
                <StatCard
                  label="Total Learners"
                  value={String(overview.totalLearners)}
                  indicator={indicatorFor()}
                  confidence={overview.confidence}
                  insufficientData={overview.insufficientData}
                />
                <StatCard
                  label="Completion Rate"
                  value={formatPct(overview.completionRate)}
                  indicator={indicatorFor()}
                  confidence={overview.confidence}
                  insufficientData={overview.insufficientData}
                />
                <StatCard
                  label="Avg Engagement"
                  value={formatPct(overview.averageEngagementScore)}
                  indicator={indicatorFor()}
                  confidence={overview.confidence}
                  insufficientData={overview.insufficientData}
                />
                <StatCard
                  label="Confusion Hotspots"
                  value={String(overview.confusionHotspotCount)}
                  indicator={indicatorFor()}
                  confidence={overview.confidence}
                  insufficientData={overview.insufficientData}
                />
              </>
            )}
          </section>

          {/* --- Per-course list --- */}
          <section aria-label="Your courses" className="mt-10">
            <h2 className="mb-4 text-lg font-semibold text-foreground">
              Your Courses
            </h2>
            {coursesQuery.isPending ? (
              <div className="space-y-3">
                <CourseRowSkeleton />
                <CourseRowSkeleton />
                <CourseRowSkeleton />
              </div>
            ) : courses.length === 0 ? (
              <div className="rounded-lg border border-border bg-surface px-5 py-16 text-center">
                <p className="text-sm font-medium text-foreground">No courses yet</p>
                <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
                  Once you create and publish a course, its affect analytics will
                  appear here.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {courses.map((course) => (
                  <CourseRow key={course.id} course={course} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
