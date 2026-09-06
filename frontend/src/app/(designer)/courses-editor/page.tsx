"use client";

import { useState } from "react";
import Link from "next/link";
import { Loader2, Plus } from "lucide-react";

import { useCourses } from "@/hooks/use-courses";
import { useCreateCourse, useDeleteCourse, useUpdateCourse } from "@/hooks/use-authoring";
import type { Course } from "@/types/course";

/**
 * The designer's course list.
 *
 * This page was a hardcoded array of three fictional courses with every button disabled and a
 * "coming soon" tooltip. The backend had exposed course CRUD the whole time; nothing called it.
 * The practical effect was that a course designer could not create a course.
 *
 * Actions are gated on `canEdit`, which the API computes from the same predicate its write
 * guards use. Seeded courses come back with `canEdit: false` because they are system content
 * and admin-only — so the row renders read-only rather than offering a Delete that would 403.
 */
export default function CoursesEditorPage() {
  const { data, isLoading, isError } = useCourses({ pageSize: 100 });
  const createCourse = useCreateCourse();
  const deleteCourse = useDeleteCourse();

  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const courses = data?.items ?? [];

  async function handleCreate() {
    if (!title.trim()) return;
    setError(null);
    try {
      await createCourse.mutateAsync({
        title: title.trim(),
        description: description.trim() || null,
      });
      setTitle("");
      setDescription("");
      setCreating(false);
    } catch {
      setError("Could not create the course. Please try again.");
    }
  }

  async function handleDelete(courseId: string) {
    setError(null);
    try {
      await deleteCourse.mutateAsync(courseId);
      setConfirmDelete(null);
    } catch {
      setError("Could not delete the course.");
    }
  }

  return (
    <div>
      <div className="mb-8 flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Courses</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Create a course, then build its structure and write its content.
          </p>
        </div>
        {!creating && (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="flex shrink-0 items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" />
            New course
          </button>
        )}
      </div>

      {creating && (
        <div className="mb-6 rounded-lg border border-border bg-surface p-5">
          <h2 className="mb-3 text-sm font-semibold text-foreground">New course</h2>
          <div className="space-y-3">
            <label className="block text-xs font-medium text-foreground">
              Title
              <input
                autoFocus
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Introduction to Databases"
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              />
            </label>
            <label className="block text-xs font-medium text-foreground">
              Description <span className="font-normal text-muted-foreground">(optional)</span>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              />
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleCreate}
                disabled={!title.trim() || createCourse.isPending}
                className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                {createCourse.isPending ? "Creating…" : "Create course"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setCreating(false);
                  setTitle("");
                  setDescription("");
                }}
                className="rounded-md border border-border px-3 py-2 text-sm font-medium text-foreground"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {error && (
        <p className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800/40 dark:bg-red-900/10 dark:text-red-400">
          {error}
        </p>
      )}

      {isLoading && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading courses…
        </p>
      )}

      {isError && (
        <p className="text-sm text-muted-foreground">Could not load courses.</p>
      )}

      {!isLoading && !isError && courses.length === 0 && (
        <div className="rounded-lg border border-dashed border-border p-10 text-center">
          <p className="text-sm font-medium text-foreground">No courses yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Create one to get started — you can add modules and lessons next.
          </p>
        </div>
      )}

      <div className="space-y-3">
        {courses.map((course) => (
          <CourseRow
            key={course.id}
            course={course}
            confirming={confirmDelete === course.id}
            onConfirmDelete={() => setConfirmDelete(course.id)}
            onCancelDelete={() => setConfirmDelete(null)}
            onDelete={() => handleDelete(course.id)}
            deleting={deleteCourse.isPending}
          />
        ))}
      </div>
    </div>
  );
}

function CourseRow({
  course,
  confirming,
  onConfirmDelete,
  onCancelDelete,
  onDelete,
  deleting,
}: {
  course: Course;
  confirming: boolean;
  onConfirmDelete: () => void;
  onCancelDelete: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  const updateCourse = useUpdateCourse();
  // `canEdit` is null only for learners, who never reach this page. Treating undefined as false
  // keeps a stale client from rendering actions it has not been told it may take.
  const editable = course.canEdit === true;

  return (
    <div className="rounded-lg border border-border bg-surface px-5 py-4">
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate font-medium text-foreground">{course.title}</h3>
            <span
              className={`rounded px-2 py-0.5 text-xs font-medium ${
                course.isPublished
                  ? "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                  : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
              }`}
            >
              {course.isPublished ? "Published" : "Draft"}
            </span>
            {!editable && (
              <span
                className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-400"
                title="Seeded course content, or a course another designer created. Only an administrator can change it."
              >
                Read-only
              </span>
            )}
          </div>
          {course.description && (
            <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
              {course.description}
            </p>
          )}
          <p className="mt-1 text-xs text-muted-foreground">
            {course.moduleCount ?? 0} module{course.moduleCount === 1 ? "" : "s"}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <Link
            href={`/courses-editor/${course.id}`}
            className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground"
          >
            {editable ? "Edit structure" : "View structure"}
          </Link>
          {editable && (
            <>
              <button
                type="button"
                onClick={() =>
                  updateCourse.mutate({
                    courseId: course.id,
                    patch: { isPublished: !course.isPublished },
                  })
                }
                disabled={updateCourse.isPending}
                className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground disabled:opacity-50"
              >
                {course.isPublished ? "Unpublish" : "Publish"}
              </button>
              <button
                type="button"
                onClick={onConfirmDelete}
                className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 dark:border-red-800/50 dark:text-red-400"
              >
                Delete
              </button>
            </>
          )}
        </div>
      </div>

      {confirming && (
        <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-4 dark:border-red-800/40 dark:bg-red-900/10">
          <p className="mb-3 text-sm text-red-800 dark:text-red-300">
            Delete <strong>{course.title}</strong>? This removes every module, lesson, section
            and block inside it, along with learner progress. It cannot be undone.
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onDelete}
              disabled={deleting}
              className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {deleting ? "Deleting…" : "Delete course"}
            </button>
            <button
              type="button"
              onClick={onCancelDelete}
              className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
