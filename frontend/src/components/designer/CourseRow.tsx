"use client";

import Link from "next/link";

import { useCourseOverview } from "@/hooks/use-analytics";
import type { Course } from "@/types/course";

interface CourseRowProps {
  course: Course;
}

/**
 * One clickable row in the dashboard per-course list. Each row carries its OWN
 * overview-derived metrics (per-course `useCourseOverview`) — there is no
 * cross-course rollup in the backend contract. Clicking navigates to that
 * course's affect-heatmap route (`/analytics/<courseId>`, the Story 7.3 target).
 */
export function CourseRow({ course }: CourseRowProps) {
  const { data, isPending, isError } = useCourseOverview(course.id);

  let metrics: string;
  if (isPending) {
    metrics = "Loading metrics…";
  } else if (isError || !data) {
    metrics = "Metrics unavailable";
  } else if (data.insufficientData) {
    metrics = "Limited data — not enough sessions yet";
  } else {
    metrics = `${data.totalLearners} learners · ${Math.round(
      data.completionRate
    )}% complete · ${Math.round(data.averageEngagementScore)}% engaged`;
  }

  return (
    <Link
      href={`/analytics/${course.id}`}
      className="flex cursor-pointer items-center justify-between rounded-lg border border-border bg-surface px-5 py-4 transition-colors hover:bg-background/50"
    >
      <div className="flex-1">
        <h3 className="font-semibold text-foreground">{course.title}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{metrics}</p>
      </div>
      <span aria-hidden="true" className="ml-4 text-muted-foreground">
        →
      </span>
    </Link>
  );
}
