"use client";

import { useState } from "react";
import { toast } from "sonner";

import { InstrumentForm, type InstrumentSubmission } from "@/components/study/InstrumentForm";
import { SUS, UEQ_S, type InstrumentDef } from "@/components/study/instruments";
import { SatisfactionSurvey, type SurveyValues } from "@/components/study/SatisfactionSurvey";
import { ThankYouSummary } from "@/components/study/ThankYouSummary";
import { useSubmitInstrument } from "@/hooks/use-instruments";
import { useSubmitSurvey } from "@/hooks/use-survey";
import { useSessionStore } from "@/stores/session-store";

type Step = "satisfaction" | "sus" | "ueq_s" | "done";

/**
 * Post-study questionnaires (Story 6.4, extended for the pilot).
 *
 * The post-assessment results screen links here. The four satisfaction items come first, then the
 * two validated scales -- SUS (usability) and UEQ-S (user experience) -- in the same order for every
 * participant, then the Thank You summary on the same page. A failed submit surfaces a toast and
 * leaves the learner on the step, never trapped and never silently advanced.
 */
export default function SurveyPage() {
  const learnerId = useSessionStore((s) => s.user?.id);
  const submitSurvey = useSubmitSurvey();
  const submitInstrument = useSubmitInstrument();
  const [step, setStep] = useState<Step>("satisfaction");

  async function handleSatisfaction(responses: SurveyValues) {
    try {
      await submitSurvey.mutateAsync(responses as Record<string, unknown>);
      setStep("sus");
    } catch {
      toast.error("Could not submit your survey. Please try again.");
    }
  }

  function instrumentStep(def: InstrumentDef, next: Step) {
    return async ({ responses, skipped, shownAt }: InstrumentSubmission) => {
      try {
        await submitInstrument.mutateAsync({
          instrument: def.name, version: def.version, responses, skipped, shownAt,
        });
        setStep(next);
      } catch {
        toast.error("Could not save your answers. Please try again.");
      }
    };
  }

  if (step === "done") return <ThankYouSummary learnerId={learnerId} />;
  if (step === "sus") {
    return (
      <InstrumentForm key="sus" def={SUS} onSubmit={instrumentStep(SUS, "ueq_s")}
        isSubmitting={submitInstrument.isPending} />
    );
  }
  if (step === "ueq_s") {
    return (
      <InstrumentForm key="ueq_s" def={UEQ_S} onSubmit={instrumentStep(UEQ_S, "done")}
        isSubmitting={submitInstrument.isPending} submitLabel="Finish" />
    );
  }
  return (
    <SatisfactionSurvey onSubmit={handleSatisfaction} isSubmitting={submitSurvey.isPending} />
  );
}
