"use client";

import Link from "next/link";

import { AssistanceHistory } from "@/components/learning/AssistanceHistory";
import { useLearnerProgress } from "@/hooks/use-progress";
import { useSessionStore } from "@/stores/session-store";

export default function ProgressPage() {
  const user = useSessionStore((s) => s.user);
  const { data, isLoading, isError } = useLearnerProgress(user?.id);

  const courses = data?.courses ?? [];
  const totalSections = courses.reduce((s, c) => s + c.totalSections, 0);
  const completedSections = courses.reduce((s, c) => s + c.completedSections, 0);
  const overallProgress =
    totalSections > 0 ? Math.round((completedSections / totalSections) * 100) : 0;

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">My Progress</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Track your learning journey across all courses
        </p>
      </div>

      {isLoading && (
        <p className="text-sm text-muted-foreground">Loading your progress…</p>
      )}

      {isError && (
        <p className="text-sm text-muted-foreground">
          Could not load your progress right now. Please try again later.
        </p>
      )}

      {!isLoading && !isError && courses.length === 0 && (
        <div className="rounded-lg border border-border bg-surface p-8 text-center">
          <p className="text-sm text-muted-foreground">
            You haven&apos;t started any courses yet.
          </p>
          <Link
            href="/courses"
            className="mt-4 inline-block rounded-md bg-primary px-4 py-2 text-sm font-semibold text-white"
          >
            Browse courses
          </Link>
        </div>
      )}

      {!isLoading && !isError && courses.length > 0 && (
        <>
          <div className="mb-8 rounded-lg border border-border bg-surface p-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-semibold text-foreground">Overall Progress</h2>
              <span className="text-sm font-semibold text-primary">{overallProgress}%</span>
            </div>
            <div className="h-2.5 w-full rounded-full bg-border">
              <div
                className="h-2.5 rounded-full bg-primary transition-all"
                style={{ width: `${overallProgress}%` }}
                role="progressbar"
                aria-valuenow={overallProgress}
                aria-valuemin={0}
                aria-valuemax={100}
              />
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              {completedSections} of {totalSections} sections completed
              {data?.quizzes && data.quizzes.answered > 0 && (
                <> · {data.quizzes.correct}/{data.quizzes.answered} quiz answers correct</>
              )}
            </p>
          </div>

          <div className="space-y-3">
            {courses.map((course) => {
              const pct = Math.round(course.percentage);
              const done = course.totalSections > 0 && course.completedSections === course.totalSections;
              return (
                <div
                  key={course.courseId}
                  className="rounded-lg border border-border bg-surface p-5"
                >
                  <div className="mb-3 flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      {done ? (
                        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-green-500 text-white">
                          <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                          </svg>
                        </span>
                      ) : (
                        <span className="flex h-5 w-5 items-center justify-center rounded-full border-2 border-border text-[10px] font-semibold text-muted-foreground">
                          {pct > 0 ? "…" : ""}
                        </span>
                      )}
                      <Link
                        href={`/courses/${course.courseId}`}
                        className="text-sm font-semibold text-foreground hover:text-primary"
                      >
                        {course.courseTitle}
                      </Link>
                    </div>
                    <span className="text-sm font-semibold text-primary">{pct}%</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="h-1.5 flex-1 rounded-full bg-border">
                      <div
                        className={`h-1.5 rounded-full transition-all ${done ? "bg-green-500" : "bg-primary"}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {course.completedSections}/{course.totalSections} sections
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/*
        Every hint delivered was recorded and nothing ever showed it back to the person who
        received it. Placed on Progress rather than a route of its own: "what help did I get" is
        the same question as "how am I doing", and a nav item per read is how menus get long.
      */}
      <div className="mt-8">
        <AssistanceHistory />
      </div>
    </div>
  );
}
