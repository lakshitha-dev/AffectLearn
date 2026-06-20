"use client";

import { Controller, useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import {
  SATISFACTION_QUESTIONS,
  type SurveyQuestion,
} from "./satisfaction-questions";

export interface SurveyValues {
  [questionId: string]: string | undefined;
}

interface SatisfactionSurveyProps {
  /** Persist the responses; resolves when the submission succeeds. */
  onSubmit: (responses: SurveyValues) => Promise<void>;
  isSubmitting?: boolean;
}

function isAnswered(question: SurveyQuestion, value: unknown): boolean {
  if (!question.required) return true;
  return typeof value === "string" && value.length > 0;
}

/**
 * Full-page post-study satisfaction survey (Story 6.4), framed "Help us improve AffectLearn".
 * Renders one 5-point Likert `radiogroup` per AC dimension (data-driven from
 * `satisfaction-questions.ts`); the submit button is gated until every required item is
 * answered. Low scores still submit — the >= 4.0/5 target is a research metric, not a gate.
 */
export function SatisfactionSurvey({
  onSubmit,
  isSubmitting = false,
}: SatisfactionSurveyProps) {
  const { control, handleSubmit, watch } = useForm<SurveyValues>({
    mode: "onChange",
  });

  const values = watch();
  const allAnswered = SATISFACTION_QUESTIONS.every((q) =>
    isAnswered(q, values[q.id]),
  );

  const submit = handleSubmit(async (data) => {
    await onSubmit(data);
  });

  return (
    <div className="space-y-6 max-w-2xl mx-auto px-8 py-12">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">
          Help us improve AffectLearn
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          You&apos;re all done with the course material. A few quick questions about your
          experience — there are no right or wrong answers.
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (allAnswered) void submit();
        }}
      >
        <div className="rounded-xl border border-border bg-surface p-6 space-y-8">
          {SATISFACTION_QUESTIONS.map((question) => (
            <Controller
              key={question.id}
              name={question.id}
              control={control}
              defaultValue={undefined}
              render={({ field }) => (
                <LikertField
                  question={question}
                  value={typeof field.value === "string" ? field.value : ""}
                  onChange={field.onChange}
                />
              )}
            />
          ))}
        </div>

        <div className="mt-6">
          <Button
            type="submit"
            size="lg"
            disabled={!allAnswered || isSubmitting}
            aria-disabled={!allAnswered || isSubmitting}
          >
            {isSubmitting ? "Submitting…" : "Submit"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function LikertField({
  question,
  value,
  onChange,
}: {
  question: SurveyQuestion;
  value: string;
  onChange: (v: string) => void;
}) {
  const labelId = `${question.id}-label`;
  return (
    <fieldset className="space-y-3">
      <legend id={labelId} className="text-sm font-medium text-foreground">
        {question.prompt}
      </legend>
      <div
        role="radiogroup"
        aria-labelledby={labelId}
        className="flex flex-wrap gap-2"
      >
        {question.options.map((option) => {
          const checked = value === option.value;
          return (
            <label
              key={option.value}
              className={cn(
                "flex items-center gap-2 rounded-lg border px-3 py-2 cursor-pointer transition-colors",
                checked
                  ? "border-primary bg-primary/5"
                  : "border-border hover:bg-accent",
              )}
            >
              <input
                type="radio"
                name={question.id}
                value={option.value}
                checked={checked}
                onChange={() => onChange(option.value)}
                className="h-4 w-4 accent-primary"
              />
              <span className="text-sm text-foreground">{option.label}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
