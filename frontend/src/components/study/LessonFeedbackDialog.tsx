"use client";

import { toast } from "sonner";

import { InstrumentForm, type InstrumentSubmission } from "./InstrumentForm";
import { LESSON_FEEDBACK } from "./instruments";
import { useSubmitInstrument } from "@/hooks/use-instruments";

/**
 * The short lesson-feedback questionnaire, shown when a participant leaves a lesson's last section.
 *
 * Asked in BOTH arms with the same wording, so the control arm's answer to "did you notice the
 * lesson changing" is the baseline the adaptive arm's is read against. Skippable, and a failed save
 * never traps the learner: they are told, and the lesson continues.
 */
export function LessonFeedbackDialog({
  context,
  onDone,
}: {
  context: Record<string, string>;
  onDone: () => void;
}) {
  const submit = useSubmitInstrument();

  async function handle({ responses, skipped, shownAt }: InstrumentSubmission) {
    try {
      await submit.mutateAsync({
        instrument: LESSON_FEEDBACK.name, version: LESSON_FEEDBACK.version,
        responses, skipped, shownAt, context,
      });
    } catch {
      toast.error("Your feedback could not be saved. You can carry on.");
    }
    onDone();
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={LESSON_FEEDBACK.title}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <div className="max-h-[90vh] w-[min(40rem,100%)] overflow-y-auto rounded-xl bg-background p-6 shadow-2xl">
        <InstrumentForm def={LESSON_FEEDBACK} onSubmit={handle} isSubmitting={submit.isPending}
          allowSkip compact />
      </div>
    </div>
  );
}
