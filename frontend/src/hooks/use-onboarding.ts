"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api-client";
import { useSessionStore } from "@/stores/session-store";

export function useGiveConsent() {
  const queryClient = useQueryClient();
  const setUser = useSessionStore((s) => s.setUser);

  return useMutation({
    mutationFn: () =>
      apiFetch("/auth/consent", {
        method: "POST",
        body: JSON.stringify({ consentGiven: true }),
      }),
    onSuccess: (data) => {
      setUser(data as Parameters<typeof setUser>[0]);
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });
}

export function useSubmitQuestionnaire() {
  return useMutation({
    mutationFn: (responses: Record<string, unknown>) =>
      apiFetch("/onboarding/questionnaire", {
        method: "POST",
        body: JSON.stringify({ responses }),
      }),
  });
}

export function useSetWebcamMode() {
  const setUser = useSessionStore((s) => s.setUser);
  return useMutation({
    mutationFn: (webcamEnabled: boolean) =>
      apiFetch("/auth/webcam-mode", {
        method: "POST",
        body: JSON.stringify({ webcamEnabled }),
      }),
    onSuccess: (data) => {
      setUser(data as Parameters<typeof setUser>[0]);
    },
  });
}