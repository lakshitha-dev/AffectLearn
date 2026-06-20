"use client";

import { useState } from "react";
import { toast } from "sonner";

import { SatisfactionSurvey, type SurveyValues } from "@/components/study/SatisfactionSurvey";
import { ThankYouSummary } from "@/components/study/ThankYouSummary";
import { useSubmitSurvey } from "@/hooks/use-survey";
import { useSessionStore } from "@/stores/session-store";

/**
 * Post-study satisfaction survey route (Story 6.4).
 *
 * The post-assessment results screen links here. On a successful submit we swap to the Thank
 * You + achievements summary on the SAME page (we do NOT navigate away — AC4). A transient
 * submit failure surfaces a toast but never traps the learner.
 */
export default function SurveyPage() {
  const learnerId = useSessionStore((s) => s.user?.id);
  const submitMutation = useSubmitSurvey();
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(responses: SurveyValues) {
    try {
      await submitMutation.mutateAsync(responses as Record<string, unknown>);
      setSubmitted(true);
    } catch {
      toast.error("Could not submit your survey. Please try again.");
    }
  }

  if (submitted) {
    return <ThankYouSummary learnerId={learnerId} />;
  }

  return (
    <SatisfactionSurvey
      onSubmit={handleSubmit}
      isSubmitting={submitMutation.isPending}
    />
  );
}
