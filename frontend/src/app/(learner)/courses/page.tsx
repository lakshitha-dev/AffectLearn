"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { CourseCard } from "@/components/learning/CourseCard";
import { CourseCardSkeleton } from "@/components/learning/CourseCardSkeleton";
import { CourseGrid } from "@/components/learning/CourseGrid";
import { CourseSearch } from "@/components/learning/CourseSearch";
import { WelcomeBackCard } from "@/components/learning/WelcomeBackCard";
import { useCourses, useEnrollments } from "@/hooks/use-courses";
import { useDebounce } from "@/hooks/use-debounce";
import { useUiStore } from "@/stores/ui-store";
import { useSessionStore } from "@/stores/session-store";
import type { Course } from "@/types/course";

// Recommended learning order: the neutral warm-up FIRST (it's the study baseline), then the
// three courses in increasing difficulty. Keeps a new learner from opening the hardest course
// cold and bailing. Matched by title keyword (titles stay topic-natural).
function courseRank(title: string): number {
  const t = title.toLowerCase();
  if (t.includes("getting comfortable") || t.includes("warm")) return 0;
  if (t.includes("foundations")) return 1;
  if (t.includes("building")) return 2;
  if (t.includes("multi-agent") || t.includes("orchestration")) return 3;
  return 50;
}
const byRank = (a: Course, b: Course) =>
  courseRank(a.title) - courseRank(b.title) || a.title.localeCompare(b.title);
const isWarmUp = (c: Course) => courseRank(c.title) === 0;

export default function CoursesPage() {
  const [searchInput, setSearchInput] = useState("");
  const debouncedSearch = useDebounce(searchInput, 300);

  const enrollmentsQuery = useEnrollments();
  const coursesQuery = useCourses({ search: debouncedSearch });
  const { welcomeBackDismissed, dismissWelcomeBack } = useUiStore();
  const user = useSessionStore((s) => s.user);

  const mostRecentEnrollment = !welcomeBackDismissed
    ? (enrollmentsQuery.data?.items?.[0] ?? null)
    : null;

  const enrolledCourses = enrollmentsQuery.data?.items ?? [];
  const allCourses = [...(coursesQuery.data?.items ?? [])].sort(byRank);
  const enrolledCourseIds = new Set(enrolledCourses.map((e) => e.courseId));
  const browseCourses = allCourses.filter(
    (course) => !enrolledCourseIds.has(course.id),
  );

  const warmup = allCourses.find(isWarmUp);
  // A brand-new learner (no enrollments yet), browsing the default catalog.
  const showStartHere =
    !enrollmentsQuery.isLoading &&
    enrolledCourses.length === 0 &&
    allCourses.length > 0 &&
    debouncedSearch.length < 2;

  const showSearchEmpty =
    !coursesQuery.isLoading &&
    debouncedSearch.length >= 2 &&
    browseCourses.length === 0;
  const showCatalogEmpty =
    !coursesQuery.isLoading &&
    debouncedSearch.length < 2 &&
    allCourses.length === 0 &&
    enrolledCourses.length === 0;

  return (
    <div className="space-y-12">
      {mostRecentEnrollment && !enrollmentsQuery.isLoading && (
        <WelcomeBackCard
          enrollment={mostRecentEnrollment}
          firstName={user?.firstName ?? null}
          onDismiss={dismissWelcomeBack}
        />
      )}

      {showStartHere && (
        <StartHere sequence={allCourses} warmup={warmup} firstName={user?.firstName ?? null} />
      )}

      {enrolledCourses.length > 0 ? (
        <section aria-labelledby="my-courses-heading" className="space-y-4">
          <h2
            id="my-courses-heading"
            className="text-2xl font-semibold text-foreground"
          >
            My Courses
          </h2>
          <CourseGrid>
            {enrolledCourses.map((enrollment) => {
              const courseShape: Course = {
                id: enrollment.courseId,
                title: enrollment.courseTitle,
                description: enrollment.courseDescription,
                estimatedDurationMinutes:
                  enrollment.courseEstimatedDurationMinutes,
                isPublished: true,
                createdAt: enrollment.createdAt,
                updatedAt: enrollment.updatedAt,
                moduleCount: enrollment.courseModuleCount,
              };
              return (
                <CourseCard
                  key={enrollment.id}
                  course={courseShape}
                  variant="enrolled"
                  progress={enrollment.progressPercentage}
                  lastAccessedAt={enrollment.lastAccessedAt}
                />
              );
            })}
          </CourseGrid>
        </section>
      ) : null}

      <section aria-labelledby="browse-heading" className="space-y-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <h2
            id="browse-heading"
            className="text-2xl font-semibold text-foreground"
          >
            Browse Courses
          </h2>
          <div className="w-full sm:max-w-sm">
            <CourseSearch value={searchInput} onChange={setSearchInput} />
          </div>
        </div>

        <div role="status" aria-live="polite" className="sr-only">
          {coursesQuery.isFetching
            ? "Loading courses"
            : `${browseCourses.length} courses available`}
        </div>

        {coursesQuery.isLoading ? (
          <CourseGrid>
            {Array.from({ length: 8 }).map((_, idx) => (
              <CourseCardSkeleton key={idx} />
            ))}
          </CourseGrid>
        ) : showSearchEmpty ? (
          <p className="rounded-lg border border-dashed border-border bg-surface p-8 text-center text-muted-foreground">
            No courses match &ldquo;{debouncedSearch}&rdquo;. Try different
            keywords.
          </p>
        ) : showCatalogEmpty ? (
          <p className="rounded-lg border border-dashed border-border bg-surface p-8 text-center text-muted-foreground">
            No courses available yet. Check back soon!
          </p>
        ) : browseCourses.length > 0 ? (
          <CourseGrid>
            {browseCourses.map((course) => (
              <CourseCard
                key={course.id}
                course={course}
                highlightText={debouncedSearch}
                recommended={debouncedSearch.length < 2 && isWarmUp(course)}
              />
            ))}
          </CourseGrid>
        ) : null}
      </section>
    </div>
  );
}

/**
 * First-run orientation for a brand-new learner: a warm welcome, plain "how this works"
 * framing, the recommended order, and a one-tap way into the warm-up — so nobody lands on a
 * bare grid of equal cards and guesses where to begin (which was the top drop-off point).
 */
function StartHere({
  sequence,
  warmup,
  firstName,
}: {
  sequence: Course[];
  warmup: Course | undefined;
  firstName: string | null;
}) {
  const beginCourse = warmup ?? sequence[0];
  return (
    <section
      aria-label="Getting started"
      className="rounded-2xl border border-border bg-surface p-6 sm:p-8 space-y-5"
    >
      <div className="space-y-1.5">
        <h1 className="text-2xl font-semibold text-foreground">
          Welcome{firstName ? `, ${firstName}` : ""} 👋
        </h1>
        <p className="text-base text-muted-foreground">
          Here&apos;s how this works: start with a short, relaxed warm-up, then work through the
          courses in order below. Some parts will feel clear and easy, some more challenging or
          slow — that&apos;s a normal part of learning. Go at your own pace.
        </p>
      </div>

      {sequence.length > 0 && (
        <ol className="space-y-1.5 text-sm">
          {sequence.map((c, i) => (
            <li key={c.id} className="flex items-center gap-2 text-foreground">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                {i + 1}
              </span>
              <span>{c.title}</span>
              {isWarmUp(c) ? (
                <span className="text-xs font-medium text-primary">· start here</span>
              ) : null}
            </li>
          ))}
        </ol>
      )}

      {beginCourse && (
        <Link href={`/courses/${beginCourse.id}`}>
          <Button size="lg">
            {warmup ? "Begin with the warm-up →" : "Begin →"}
          </Button>
        </Link>
      )}
    </section>
  );
}
