"use client";

import Link from "next/link";
import { Loader2 } from "lucide-react";

import { useCourse, useCourses } from "@/hooks/use-courses";
import type { CourseDetail } from "@/types/course";

/**
 * Jump straight to a lesson.
 *
 * This was an empty state whose only action was "Go to Courses" — a nav item whose entire
 * content was a link to another nav item. Now that `/courses-editor` is real, the honest fix is
 * either to delete this page or to make it do something the courses page does not, and a flat
 * list of every lesson is genuinely faster than expanding a tree when you already know which
 * lesson you want.
 *
 * Scoped to courses the caller may edit. Showing lessons whose editor opens read-only would
 * make this a list of things you cannot do.
 */
export default function ContentEditorPage() {
  const { data, isLoading } = useCourses({ pageSize: 100 });
  const editable = (data?.items ?? []).filter((c) => c.canEdit === true);

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Content editor</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every lesson you can edit, in one list. Use{" "}
          <Link href="/courses-editor" className="underline">
            Courses
          </Link>{" "}
          to add or rearrange them.
        </p>
      </div>

      {isLoading && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </p>
      )}

      {!isLoading && editable.length === 0 && (
        <div className="rounded-lg border border-dashed border-border p-10 text-center">
          <p className="text-sm font-medium text-foreground">Nothing to edit yet</p>
          <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
            Courses you create appear here. Seeded courses and other designers&apos; courses are
            read-only, so they are not listed.
          </p>
          <Link
            href="/courses-editor"
            className="mt-5 inline-flex rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            Create a course
          </Link>
        </div>
      )}

      <div className="space-y-6">
        {editable.map((course) => (
          <CourseLessons key={course.id} courseId={course.id} title={course.title} />
        ))}
      </div>
    </div>
  );
}

function CourseLessons({ courseId, title }: { courseId: string; title: string }) {
  // The list endpoint returns courses without their tree, so each course is fetched for its
  // lessons. React Query dedupes and caches these against the same key the structure builder
  // uses, so opening a course afterwards is served from cache rather than refetched.
  const { data: course, isLoading } = useCourse(courseId);

  const lessons = flattenLessons(course);

  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold text-foreground">{title}</h2>
      {isLoading && <p className="text-xs text-muted-foreground">Loading lessons…</p>}
      {!isLoading && lessons.length === 0 && (
        <p className="text-xs text-muted-foreground">
          No lessons yet.{" "}
          <Link href={`/courses-editor/${courseId}`} className="underline">
            Add some
          </Link>
          .
        </p>
      )}
      <ul className="space-y-1.5">
        {lessons.map((lesson) => (
          <li key={lesson.lessonId}>
            <Link
              href={`/editor/${courseId}/${lesson.moduleId}/${lesson.lessonId}`}
              className="flex items-center justify-between rounded-md border border-border bg-surface px-4 py-2.5 hover:bg-background/50"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm text-foreground">{lesson.title}</span>
                <span className="block truncate text-xs text-muted-foreground">
                  {lesson.moduleTitle}
                </span>
              </span>
              <span className="shrink-0 text-xs text-muted-foreground">
                {lesson.sectionCount} section{lesson.sectionCount === 1 ? "" : "s"}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

interface FlatLesson {
  lessonId: string;
  moduleId: string;
  title: string;
  moduleTitle: string;
  sectionCount: number;
}

/** Course tree -> flat lesson list, in author order. */
function flattenLessons(course: CourseDetail | undefined): FlatLesson[] {
  if (!course?.modules) return [];
  return [...course.modules]
    .sort((a, b) => a.sortOrder - b.sortOrder)
    .flatMap((module) =>
      [...(module.lessons ?? [])]
        .sort((a, b) => a.sortOrder - b.sortOrder)
        .map((lesson) => ({
          lessonId: lesson.id,
          moduleId: module.id,
          title: lesson.title,
          moduleTitle: module.title,
          sectionCount: lesson.sections?.length ?? 0,
        })),
    );
}
