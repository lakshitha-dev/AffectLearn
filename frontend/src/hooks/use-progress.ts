"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiFetch, ApiRequestError } from "@/lib/api-client";
import type {
  CourseProgressResponse,
  LessonProgressResponse,
  ResumeTarget,
  SectionProgress,
} from "@/types/progress";

export const COURSE_PROGRESS_KEY = "courseProgress";
export const LESSON_PROGRESS_KEY = "lessonProgress";

const STALE_1_MIN = 60_000;

export function useCourseProgress(courseId: string | undefined) {
  return useQuery<CourseProgressResponse>({
    queryKey: [COURSE_PROGRESS_KEY, courseId],
    queryFn: () =>
      apiFetch<CourseProgressResponse>(`/courses/${courseId}/progress`),
    enabled: Boolean(courseId),
    staleTime: STALE_1_MIN,
  });
}

export function useLessonProgress(lessonId: string | undefined) {
  return useQuery<LessonProgressResponse>({
    queryKey: [LESSON_PROGRESS_KEY, lessonId],
    queryFn: () =>
      apiFetch<LessonProgressResponse>(`/lessons/${lessonId}/progress`),
    enabled: Boolean(lessonId),
    staleTime: STALE_1_MIN,
  });
}

export const RESUME_TARGET_KEY = "resumeTarget";

export function buildResumeUrl(target: ResumeTarget): string {
  return `/courses/${target.courseId}/modules/${target.moduleId}/lessons/${target.lessonId}#section-${target.sectionId}`;
}

export function useResumeTarget(courseId: string | undefined) {
  return useQuery<ResumeTarget | null>({
    queryKey: [RESUME_TARGET_KEY, courseId],
    queryFn: async () => {
      try {
        return await apiFetch<ResumeTarget>(`/enrollments/${courseId}/resume`);
      } catch (err) {
        if (err instanceof ApiRequestError) {
          const code = err.errorCode;
          if (code === "NOT_ENROLLED" || code === "COURSE_EMPTY") return null;
        }
        throw err;
      }
    },
    enabled: Boolean(courseId),
    staleTime: STALE_1_MIN,
  });
}

export function useMarkSectionComplete(
  courseId: string,
  lessonId: string,
) {
  const queryClient = useQueryClient();

  return useMutation<
    SectionProgress,
    Error,
    { sectionId: string },
    { prev?: CourseProgressResponse }
  >({
    mutationFn: ({ sectionId }) =>
      apiFetch<SectionProgress>("/section-progress", {
        method: "POST",
        body: JSON.stringify({ sectionId }),
      }),
    retry: (failureCount, error) => {
      if (failureCount >= 3) return false;
      // Only retry on network errors (TypeError), not HTTP 4xx/5xx
      return error instanceof TypeError;
    },
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 4000),
    onMutate: async ({ sectionId }) => {
      await queryClient.cancelQueries({ queryKey: [COURSE_PROGRESS_KEY, courseId] });
      const prev = queryClient.getQueryData<CourseProgressResponse>([
        COURSE_PROGRESS_KEY,
        courseId,
      ]);
      queryClient.setQueryData<CourseProgressResponse>(
        [COURSE_PROGRESS_KEY, courseId],
        (old) =>
          old
            ? {
                ...old,
                completedSectionIds: [...old.completedSectionIds, sectionId],
              }
            : old,
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) {
        queryClient.setQueryData([COURSE_PROGRESS_KEY, courseId], ctx.prev);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: [COURSE_PROGRESS_KEY, courseId] });
      queryClient.invalidateQueries({ queryKey: [LESSON_PROGRESS_KEY, lessonId] });
      queryClient.invalidateQueries({ queryKey: ["enrollments"] });
    },
  });
}
