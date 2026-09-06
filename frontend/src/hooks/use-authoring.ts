"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";
import type { ContentBlock, Course, Lesson, Module, Section } from "@/types/course";

/**
 * Authoring mutations for the whole content tree.
 *
 * The backend has exposed full CRUD for course, module, lesson, section and content block since
 * the content model was built. Nothing on the designer side ever called it: `/courses-editor`
 * was a hardcoded array of three fake courses with every button disabled, so a designer could
 * edit an existing lesson's text but could not create a course, add a module, or reorder
 * anything. This module is the missing half.
 *
 * INVALIDATION
 *
 * Every mutation invalidates the `courses` key. The structure builder reads the whole tree from
 * one `GET /courses/{id}` (`useCourse`), so a narrower invalidation would leave the visible tree
 * disagreeing with the database after a nested edit — the failure mode being a section that
 * still appears after it was deleted.
 *
 * SORT ORDER
 *
 * `sortOrder` is unique per parent in the database, so two siblings can never share one. That
 * makes a naive swap fail: writing A=1 while B is still 1 violates the constraint. `reorder`
 * below therefore moves through a parking slot, which is documented where it happens.
 */

const COURSES_KEY = "courses";

function useTreeMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation<TResult, Error, TArgs>({
    mutationFn: fn,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [COURSES_KEY] });
    },
  });
}

/* ------------------------------------------------------------------ */
/* Course                                                              */
/* ------------------------------------------------------------------ */

export interface CourseInput {
  title: string;
  description?: string | null;
  estimatedDurationMinutes?: number | null;
  learningObjectives?: string | null;
  isPublished?: boolean;
}

export function useCreateCourse() {
  return useTreeMutation<CourseInput, Course>((body) =>
    apiFetch<Course>("/courses", { method: "POST", body: JSON.stringify(body) }),
  );
}

export function useUpdateCourse() {
  return useTreeMutation<{ courseId: string; patch: Partial<CourseInput> }, Course>(
    ({ courseId, patch }) =>
      apiFetch<Course>(`/courses/${courseId}`, {
        method: "PUT",
        body: JSON.stringify(patch),
      }),
  );
}

export function useDeleteCourse() {
  return useTreeMutation<string, void>((courseId) =>
    apiFetch<void>(`/courses/${courseId}`, { method: "DELETE" }),
  );
}

/* ------------------------------------------------------------------ */
/* Module                                                              */
/* ------------------------------------------------------------------ */

export function useCreateModule() {
  return useTreeMutation<
    { courseId: string; title: string; description?: string | null; sortOrder: number },
    Module
  >(({ courseId, ...body }) =>
    apiFetch<Module>(`/courses/${courseId}/modules`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function useUpdateModule() {
  return useTreeMutation<
    { moduleId: string; patch: { title?: string; description?: string | null; sortOrder?: number } },
    Module
  >(({ moduleId, patch }) =>
    apiFetch<Module>(`/courses/modules/${moduleId}`, {
      method: "PUT",
      body: JSON.stringify(patch),
    }),
  );
}

export function useDeleteModule() {
  return useTreeMutation<string, void>((moduleId) =>
    apiFetch<void>(`/courses/modules/${moduleId}`, { method: "DELETE" }),
  );
}

/* ------------------------------------------------------------------ */
/* Lesson                                                              */
/* ------------------------------------------------------------------ */

export function useCreateLesson() {
  return useTreeMutation<
    { moduleId: string; title: string; description?: string | null; sortOrder: number },
    Lesson
  >(({ moduleId, ...body }) =>
    apiFetch<Lesson>(`/courses/modules/${moduleId}/lessons`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function useUpdateLesson() {
  return useTreeMutation<
    { lessonId: string; patch: { title?: string; description?: string | null; sortOrder?: number } },
    Lesson
  >(({ lessonId, patch }) =>
    apiFetch<Lesson>(`/courses/lessons/${lessonId}`, {
      method: "PUT",
      body: JSON.stringify(patch),
    }),
  );
}

export function useDeleteLesson() {
  return useTreeMutation<string, void>((lessonId) =>
    apiFetch<void>(`/courses/lessons/${lessonId}`, { method: "DELETE" }),
  );
}

/* ------------------------------------------------------------------ */
/* Section                                                             */
/* ------------------------------------------------------------------ */

export function useCreateSection() {
  return useTreeMutation<
    { lessonId: string; title: string; sortOrder: number; estimatedDurationMinutes?: number },
    Section
  >(({ lessonId, ...body }) =>
    apiFetch<Section>(`/courses/lessons/${lessonId}/sections`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function useUpdateSection() {
  return useTreeMutation<
    {
      sectionId: string;
      patch: { title?: string; sortOrder?: number; estimatedDurationMinutes?: number };
    },
    Section
  >(({ sectionId, patch }) =>
    apiFetch<Section>(`/courses/sections/${sectionId}`, {
      method: "PUT",
      body: JSON.stringify(patch),
    }),
  );
}

export function useDeleteSection() {
  return useTreeMutation<string, void>((sectionId) =>
    apiFetch<void>(`/courses/sections/${sectionId}`, { method: "DELETE" }),
  );
}

/* ------------------------------------------------------------------ */
/* Content block                                                       */
/* ------------------------------------------------------------------ */

export function useCreateContentBlock() {
  return useTreeMutation<
    {
      sectionId: string;
      blockType: ContentBlock["blockType"];
      content: Record<string, unknown>;
      sortOrder: number;
    },
    ContentBlock
  >(({ sectionId, ...body }) =>
    apiFetch<ContentBlock>(`/courses/sections/${sectionId}/content-blocks`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export function useUpdateContentBlock() {
  return useTreeMutation<
    {
      blockId: string;
      patch: {
        blockType?: ContentBlock["blockType"];
        content?: Record<string, unknown>;
        sortOrder?: number;
      };
    },
    ContentBlock
  >(({ blockId, patch }) =>
    apiFetch<ContentBlock>(`/courses/content-blocks/${blockId}`, {
      method: "PUT",
      body: JSON.stringify(patch),
    }),
  );
}

export function useDeleteContentBlock() {
  return useTreeMutation<string, void>((blockId) =>
    apiFetch<void>(`/courses/content-blocks/${blockId}`, { method: "DELETE" }),
  );
}

/* ------------------------------------------------------------------ */
/* Reordering                                                          */
/* ------------------------------------------------------------------ */

/** Anything the builder can reorder: siblings with a unique `sortOrder` under one parent. */
export interface Orderable {
  id: string;
  sortOrder: number;
}

/**
 * Swap two siblings' positions.
 *
 * `sortOrder` carries a UNIQUE(parent, sort_order) constraint, so the obvious implementation —
 * write A's order to B, then B's to A — fails on the first write, because for that instant two
 * rows hold the same value. Moving through a temporary slot outside the used range avoids the
 * collision without needing a transaction the REST API does not offer.
 *
 * The parking value is derived from the highest order in the list rather than a fixed sentinel,
 * so it cannot collide with a real position however long the list grows.
 */
export async function swapOrder(
  items: Orderable[],
  a: Orderable,
  b: Orderable,
  update: (id: string, sortOrder: number) => Promise<unknown>,
): Promise<void> {
  const parking = Math.max(...items.map((i) => i.sortOrder), 0) + 1;
  await update(a.id, parking);
  await update(b.id, a.sortOrder);
  await update(a.id, b.sortOrder);
}

/** The next free position at the end of a sibling list. */
export function nextSortOrder(items: Orderable[]): number {
  return items.length === 0 ? 0 : Math.max(...items.map((i) => i.sortOrder)) + 1;
}
