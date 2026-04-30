"use client";

import { use } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { EnrollButton } from "@/components/learning/EnrollButton";
import { useCourse, useEnrollmentStatus } from "@/hooks/use-courses";

interface PageProps {
  params: Promise<{ courseId: string }>;
}

function formatDuration(minutes: number | null | undefined): string {
  if (minutes == null) return "Self-paced";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round((minutes / 60) * 10) / 10;
  return `${hours} h`;
}

export default function CourseOverviewPage({ params }: PageProps) {
  const { courseId } = use(params);
  const courseQuery = useCourse(courseId);
  const enrollmentQuery = useEnrollmentStatus(courseId);

  if (courseQuery.isLoading) {
    return <CourseOverviewSkeleton />;
  }

  if (courseQuery.error || !courseQuery.data) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">Course not found</h1>
        <p className="text-muted-foreground">
          This course may have been removed or isn&apos;t published yet.
        </p>
        <Link href="/courses">
          <Button variant="outline">Back to courses</Button>
        </Link>
      </div>
    );
  }

  const course = courseQuery.data;
  const lessonsTotal = course.modules.reduce(
    (acc, mod) => acc + (mod.lessons?.length ?? 0),
    0,
  );

  return (
    <article className="space-y-8">
      <header className="space-y-3">
        <Link
          href="/courses"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← All courses
        </Link>
        <h1 className="text-3xl font-semibold text-foreground">{course.title}</h1>
        {course.description ? (
          <p className="max-w-3xl text-base text-muted-foreground">
            {course.description}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span>{formatDuration(course.estimatedDurationMinutes)}</span>
          <span>
            {course.modules.length}{" "}
            {course.modules.length === 1 ? "module" : "modules"}
          </span>
          <span>
            {lessonsTotal} {lessonsTotal === 1 ? "lesson" : "lessons"}
          </span>
        </div>
        <div className="pt-2">
          <EnrollButton
            courseId={course.id}
            enrollment={enrollmentQuery.data}
            isLoading={enrollmentQuery.isLoading}
          />
        </div>
      </header>

      {course.learningObjectives ? (
        <section aria-labelledby="objectives-heading" className="space-y-3">
          <h2
            id="objectives-heading"
            className="text-2xl font-semibold text-foreground"
          >
            Learning objectives
          </h2>
          <p className="whitespace-pre-line text-base text-muted-foreground">
            {course.learningObjectives}
          </p>
        </section>
      ) : null}

      <section aria-labelledby="modules-heading" className="space-y-4">
        <h2
          id="modules-heading"
          className="text-2xl font-semibold text-foreground"
        >
          Course content
        </h2>
        {course.modules.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border bg-surface p-6 text-muted-foreground">
            Module structure coming soon.
          </p>
        ) : (
          <ol className="space-y-3">
            {course.modules.map((mod, idx) => (
              <li
                key={mod.id}
                className="rounded-lg border border-border bg-surface p-4"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="text-base font-medium text-foreground">
                    <span className="mr-2 text-muted-foreground">
                      {idx + 1}.
                    </span>
                    {mod.title}
                  </h3>
                  <span className="text-xs text-muted-foreground">
                    {(mod.lessons?.length ?? 0)}{" "}
                    {(mod.lessons?.length ?? 0) === 1 ? "lesson" : "lessons"}
                  </span>
                </div>
                {mod.description ? (
                  <p className="mt-1 text-sm text-muted-foreground">
                    {mod.description}
                  </p>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </section>
    </article>
  );
}

function CourseOverviewSkeleton() {
  return (
    <div role="status" aria-label="Loading course" className="animate-pulse space-y-8">
      <div className="space-y-3">
        <div className="h-4 w-24 rounded bg-border" />
        <div className="h-8 w-2/3 rounded bg-border" />
        <div className="h-4 w-full max-w-2xl rounded bg-border" />
        <div className="h-4 w-3/4 max-w-xl rounded bg-border" />
      </div>
      <div className="h-10 w-32 rounded bg-border" />
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, idx) => (
          <div
            key={idx}
            className="h-20 rounded-lg border border-border bg-surface"
          />
        ))}
      </div>
    </div>
  );
}
