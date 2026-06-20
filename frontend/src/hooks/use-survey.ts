"use client";

import { useMutation } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";

/**
 * Submit the post-study satisfaction survey (Story 6.4).
 *
 * Mirrors `useSubmitQuestionnaire` (use-onboarding.ts): POSTs `{ responses }` to
 * `/surveys/satisfaction`. The endpoint is an idempotent upsert on the caller's own row and
 * never trusts a body `user_id`.
 */
export function useSubmitSurvey() {
  return useMutation({
    mutationFn: (responses: Record<string, unknown>) =>
      apiFetch("/surveys/satisfaction", {
        method: "POST",
        body: JSON.stringify({ responses }),
      }),
  });
}
