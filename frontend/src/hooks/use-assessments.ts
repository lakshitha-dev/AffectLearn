"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, ApiRequestError } from "@/lib/api-client";
import type { AnswerPayload, Assessment, AttemptResult } from "@/types/assessment";

const ASSESSMENT_KEY = "assessment";
const ATTEMPT_KEY = "latestAttempt";

export function useAssessment(moduleId: string | undefined, type: "pre" | "post") {
  return useQuery<Assessment | null>({
    queryKey: [ASSESSMENT_KEY, moduleId, type],
    queryFn: async () => {
      try {
        return await apiFetch<Assessment>(
          `/assessments?module_id=${moduleId}&type=${type}`
        );
      } catch (err) {
        if (err instanceof ApiRequestError && err.status === 404) return null;
        throw err;
      }
    },
    enabled: Boolean(moduleId),
    staleTime: 5 * 60 * 1000,
  });
}

export function useLatestAttempt(assessmentId: string | undefined) {
  return useQuery<AttemptResult | null>({
    queryKey: [ATTEMPT_KEY, assessmentId],
    queryFn: async () => {
      try {
        return await apiFetch<AttemptResult>(
          `/assessments/${assessmentId}/attempts/latest`
        );
      } catch (err) {
        if (err instanceof ApiRequestError && err.status === 404) return null;
        throw err;
      }
    },
    enabled: Boolean(assessmentId),
    staleTime: 60_000,
  });
}

export function useSubmitAttempt() {
  const queryClient = useQueryClient();
  return useMutation<
    AttemptResult,
    Error,
    { assessmentId: string; answers: AnswerPayload[] }
  >({
    mutationFn: ({ assessmentId, answers }) =>
      apiFetch<AttemptResult>(`/assessments/${assessmentId}/attempts`, {
        method: "POST",
        body: JSON.stringify({ answers }),
      }),
    onSuccess: (_, { assessmentId }) => {
      queryClient.invalidateQueries({ queryKey: [ATTEMPT_KEY, assessmentId] });
    },
  });
}