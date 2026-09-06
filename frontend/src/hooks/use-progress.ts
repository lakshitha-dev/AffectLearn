"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiFetch, ApiRequestError } from "@/lib/api-client";
import type { SectionSignals } from "@/hooks/use-section-signals";
import type {
  CourseProgressResponse,
  LearnerProgressResponse,
  LessonProgressResponse,
  ResumeTarget,
  SectionProgress,
} from "@/types/progress";

export const COURSE_PROGRESS_KEY = "courseProgress";
export const LESSON_PROGRESS_KEY = "lessonProgress";
export const LEARNER_PROGRESS_KEY = "learnerProgress";

const STALE_1_MIN = 60_000;

/**
 * Learner-progress aggregate (Story 4.6) — reused by the Story 6.4 achievements summary.
 * Returns per-course completion %, the completed-section history, and the quiz tally for the
 * given learner. The backend enforces that a learner may read only their own progress.
 */
export function useLearnerProgress(learnerId: string | undefined) {
  return useQuery<LearnerProgressResponse>({
    queryKey: [LEARNER_PROGRESS_KEY, learnerId],
    queryFn: () =>
      apiFetch<LearnerProgressResponse>(`/learner-profiles/${learnerId}/progress`),
    enabled: Boolean(learnerId),
    staleTime: STALE_1_MIN,
  });
}

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
    { sectionId: string; interactionSignals?: SectionSignals },
    { prev?: CourseProgressResponse }
  >({
    // `interactionSignals` carries the per-section confusion counters (dwell, back-navigation,
    // show-answer, quiz retries). Sent from the client because the backend cannot derive them:
    // research events go to a Redis stream drained asynchronously into Postgres, so a section's
    // events are not queryable at completion time. Optional — omitting it must still complete
    // the section, which is why the server field is nullable.
    mutationFn: ({ sectionId, interactionSignals }) =>
      apiFetch<SectionProgress>("/section-progress", {
        method: "POST",
        body: JSON.stringify(
          interactionSignals ? { sectionId, interactionSignals } : { sectionId },
        ),
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

interface QuizResponsePayload {
  contentBlockId: string;
  selectedAnswers: string[];
  isCorrect: boolean;
  responseTimeMs: number;
  sectionId: string;
  /**
   * The server-issued `adaptationId` of the help that was on screen when the learner answered.
   *
   * This is the only moment the two halves of the question "did the help work?" are in the same
   * place. The hint was delivered over the WebSocket minutes ago; the answer is going out over
   * REST now. Nothing on the server can join them unless the client carries the id across, so
   * omitting it here silently reduces the assistance ledger to "help was offered" with no
   * record of what happened next.
   *
   * Undefined for the great majority of answers, which follow no intervention at all.
   */
  assistanceId?: string;
}

/**
 * Records a quiz answer + its time-to-answer (frustration/deliberation probe). The backend
 * persists it as an append-only attempt, updates the per-block summary, resolves any assistance
 * outcome, and emits a `quiz_submitted` research event. Best-effort — never surfaces errors to
 * the learner.
 */
export function useRecordQuizResponse() {
  return useMutation<unknown, Error, QuizResponsePayload>({
    mutationFn: (body) =>
      apiFetch("/quiz-responses", { method: "POST", body: JSON.stringify(body) }),
    retry: (n, err) => n < 2 && err instanceof TypeError,
  });
}
