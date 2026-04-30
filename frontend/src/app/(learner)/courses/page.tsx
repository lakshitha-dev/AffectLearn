"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { CourseCard } from "@/components/learning/CourseCard";
import { CourseCardSkeleton } from "@/components/learning/CourseCardSkeleton";
import { CourseGrid } from "@/components/learning/CourseGrid";
import { CourseSearch } from "@/components/learning/CourseSearch";
import { useCourses, useEnrollments } from "@/hooks/use-courses";
import { useDebounce } from "@/hooks/use-debounce";
import type { Course } from "@/types/course";

export default function CoursesPage() {
  const [searchInput, setSearchInput] = useState("");
  const debouncedSearch = useDebounce(searchInput, 300);

  const enrollmentsQuery = useEnrollments();
  const coursesQuery = useCourses({ search: debouncedSearch });

  const enrolledCourses = enrollmentsQuery.data?.items ?? [];
  const allCourses = coursesQuery.data?.items ?? [];
  const enrolledCourseIds = new Set(enrolledCourses.map((e) => e.courseId));
  const browseCourses = allCourses.filter(
    (course) => !enrolledCourseIds.has(course.id),
  );

  const showSearchEmpty =
    !coursesQuery.isLoading &&
    debouncedSearch.length >= 2 &&
    browseCourses.length === 0;
  const showCatalogEmpty =
    !coursesQuery.isLoading &&
    debouncedSearch.length < 2 &&
    allCourses.length === 0 &&
    enrolledCourses.length === 0;
  const showNewLearnerHint =
    !enrollmentsQuery.isLoading && enrolledCourses.length === 0 && allCourses.length > 0;

  return (
    <div className="space-y-12">
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
              />
            ))}
          </CourseGrid>
        ) : showNewLearnerHint ? (
          <NewLearnerHint />
        ) : null}
      </section>
    </div>
  );
}

function NewLearnerHint() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border bg-surface p-8 text-center">
      <p className="text-base text-muted-foreground">
        Ready to start learning? Choose your first course.
      </p>
      <Link href="#browse-heading">
        <Button>Browse Courses</Button>
      </Link>
    </div>
  );
}
