import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";

/**
 * Designer-side assessment authoring.
 *
 * The create endpoints existed and nothing called them, so the pre/post assessments FR9 depends
 * on could only be brought into existence by hand-crafted HTTP requests. These wrap the full set
 * the authoring screen needs.
 *
 * Note the shape difference from `use-assessments.ts`: these carry `isCorrect`, because the
 * learner-facing responses deliberately omit it so the answers cannot be read out of the payload
 * of the test a learner is sitting.
 */

export interface AuthoringOption {
  id?: string;
  text: string;
  isCorrect: boolean;
  sortOrder: number;
}

export interface AuthoringQuestion {
  id: string;
  text: string;
  sortOrder: number;
  explanation: string | null;
  options: AuthoringOption[];
}

export interface AuthoringAssessment {
  id: string;
  moduleId: string;
  assessmentType: "pre" | "post";
  title: string;
  questions: AuthoringQuestion[];
}

const KEY = "assessmentAuthoring";

export function useModuleAssessments(moduleId: string | undefined) {
  return useQuery<AuthoringAssessment[]>({
    queryKey: [KEY, moduleId],
    queryFn: () => apiFetch<AuthoringAssessment[]>(`/assessments/by-module/${moduleId}`),
    enabled: Boolean(moduleId),
  });
}

/** Invalidate the module's authoring view after any write. */
function useRefresh(moduleId: string | undefined) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: [KEY, moduleId] });
}

export function useCreateAssessment(moduleId: string | undefined) {
  const refresh = useRefresh(moduleId);
  return useMutation<
    AuthoringAssessment,
    Error,
    { assessmentType: "pre" | "post"; title: string }
  >({
    mutationFn: (body) =>
      apiFetch<AuthoringAssessment>("/assessments", {
        method: "POST",
        body: JSON.stringify({ ...body, moduleId }),
      }),
    onSuccess: refresh,
  });
}

export function useAddQuestion(moduleId: string | undefined) {
  const refresh = useRefresh(moduleId);
  return useMutation<
    AuthoringQuestion,
    Error,
    {
      assessmentId: string;
      text: string;
      sortOrder: number;
      explanation: string | null;
      options: AuthoringOption[];
    }
  >({
    mutationFn: ({ assessmentId, ...body }) =>
      apiFetch<AuthoringQuestion>(`/assessments/${assessmentId}/questions`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: refresh,
  });
}

export function useUpdateQuestion(moduleId: string | undefined) {
  const refresh = useRefresh(moduleId);
  return useMutation<
    AuthoringQuestion,
    Error,
    {
      questionId: string;
      text: string;
      sortOrder: number;
      explanation: string | null;
      options: AuthoringOption[];
    }
  >({
    mutationFn: ({ questionId, ...body }) =>
      apiFetch<AuthoringQuestion>(`/assessments/questions/${questionId}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: refresh,
  });
}

export function useDeleteQuestion(moduleId: string | undefined) {
  const refresh = useRefresh(moduleId);
  return useMutation<void, Error, { questionId: string }>({
    mutationFn: ({ questionId }) =>
      apiFetch<void>(`/assessments/questions/${questionId}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
}

export function useDeleteAssessment(moduleId: string | undefined) {
  const refresh = useRefresh(moduleId);
  return useMutation<void, Error, { assessmentId: string }>({
    mutationFn: ({ assessmentId }) =>
      apiFetch<void>(`/assessments/${assessmentId}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
}
