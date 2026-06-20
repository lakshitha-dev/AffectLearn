"use client";

import { useState } from "react";
import { useForm, Controller } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { StepIndicator } from "./StepIndicator";
import {
  QUESTIONNAIRE_SECTIONS,
  TOTAL_SECTIONS,
  type MatrixQuestion,
  type MultiQuestion,
  type Question,
  type SingleQuestion,
} from "./questionnaire-questions";

export interface QuestionnaireValues {
  [questionId: string]: string | string[] | Record<string, string> | undefined;
}

interface QuestionnaireStepProps {
  /** Persist the responses; resolves when the submission succeeds. */
  onSubmit: (responses: QuestionnaireValues) => Promise<void>;
  isSubmitting?: boolean;
  /** Onboarding-wide step indicator (the questionnaire is one outer onboarding step). */
  currentStep: number;
  totalSteps: number;
}

function isAnswered(question: Question, value: unknown): boolean {
  if (!question.required) return true;
  if (question.type === "matrix") {
    const m = question as MatrixQuestion;
    if (typeof value !== "object" || value === null) return false;
    const record = value as Record<string, string>;
    return m.rows.every((row) => Boolean(record[row.value]));
  }
  if (question.type === "multi") return true; // multi-select is optional by spec
  return typeof value === "string" && value.length > 0;
}

export function QuestionnaireStep({
  onSubmit,
  isSubmitting = false,
  currentStep,
  totalSteps,
}: QuestionnaireStepProps) {
  const [sectionIndex, setSectionIndex] = useState(0);
  const { control, handleSubmit, watch } = useForm<QuestionnaireValues>({
    defaultValues: { Q9: [] },
    mode: "onChange",
  });

  const section = QUESTIONNAIRE_SECTIONS[sectionIndex];
  const isLastSection = sectionIndex === TOTAL_SECTIONS - 1;
  const values = watch();

  const sectionComplete = section.questions.every((q) =>
    isAnswered(q, values[q.id]),
  );

  function goBack() {
    setSectionIndex((i) => Math.max(0, i - 1));
  }

  function goNext() {
    if (!sectionComplete) return;
    setSectionIndex((i) => Math.min(TOTAL_SECTIONS - 1, i + 1));
  }

  const submit = handleSubmit(async (data) => {
    await onSubmit(data);
  });

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <StepIndicator currentStep={currentStep} totalSteps={totalSteps} />

      <div>
        <h1 className="text-2xl font-semibold text-foreground">
          Help us personalize your experience
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          A few quick questions so we can tailor your learning. There are no right or wrong
          answers.
        </p>
      </div>

      <p className="text-sm font-medium text-muted-foreground" aria-live="polite" role="status">
        Section {sectionIndex + 1} of {TOTAL_SECTIONS}
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (isLastSection) void submit();
        }}
      >
        <div className="rounded-xl border border-border bg-surface p-6 space-y-8">
          <h2 className="text-lg font-semibold text-foreground">{section.title}</h2>
          {section.questions.map((question) => (
            <Controller
              key={question.id}
              name={question.id}
              control={control}
              defaultValue={question.type === "multi" ? [] : undefined}
              render={({ field }) => (
                <QuestionField
                  question={question}
                  value={field.value}
                  onChange={field.onChange}
                />
              )}
            />
          ))}
        </div>

        <div className="mt-6 flex gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={goBack}
            disabled={sectionIndex === 0}
          >
            Back
          </Button>
          {isLastSection ? (
            <Button
              type="submit"
              disabled={!sectionComplete || isSubmitting}
              aria-disabled={!sectionComplete || isSubmitting}
            >
              {isSubmitting ? "Saving…" : "Finish"}
            </Button>
          ) : (
            <Button
              type="button"
              onClick={goNext}
              disabled={!sectionComplete}
              aria-disabled={!sectionComplete}
            >
              Next
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}

interface QuestionFieldProps {
  question: Question;
  value: string | string[] | Record<string, string> | undefined;
  onChange: (value: string | string[] | Record<string, string>) => void;
}

function QuestionField({ question, value, onChange }: QuestionFieldProps) {
  if (question.type === "multi") {
    return (
      <MultiSelectField
        question={question as MultiQuestion}
        value={Array.isArray(value) ? value : []}
        onChange={onChange}
      />
    );
  }
  if (question.type === "matrix") {
    return (
      <MatrixField
        question={question as MatrixQuestion}
        value={(value as Record<string, string>) ?? {}}
        onChange={onChange}
      />
    );
  }
  return (
    <SingleSelectField
      question={question as SingleQuestion}
      value={typeof value === "string" ? value : ""}
      onChange={onChange}
    />
  );
}

function SingleSelectField({
  question,
  value,
  onChange,
}: {
  question: SingleQuestion;
  value: string;
  onChange: (v: string) => void;
}) {
  const labelId = `${question.id}-label`;
  return (
    <fieldset className="space-y-3">
      <legend id={labelId} className="text-sm font-medium text-foreground">
        {question.prompt}
      </legend>
      <div role="radiogroup" aria-labelledby={labelId} className="space-y-2">
        {question.options.map((option) => (
          <label
            key={option.value}
            className={cn(
              "flex items-center gap-3 rounded-lg border px-4 py-2.5 cursor-pointer transition-colors",
              value === option.value
                ? "border-primary bg-primary/5"
                : "border-border hover:bg-accent",
            )}
          >
            <input
              type="radio"
              name={question.id}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              className="h-4 w-4 accent-primary"
            />
            <span className="text-sm text-foreground">{option.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function MultiSelectField({
  question,
  value,
  onChange,
}: {
  question: MultiQuestion;
  value: string[];
  onChange: (v: string[]) => void;
}) {
  const labelId = `${question.id}-label`;
  function toggle(optionValue: string) {
    if (value.includes(optionValue)) {
      onChange(value.filter((v) => v !== optionValue));
    } else {
      onChange([...value, optionValue]);
    }
  }
  // The <fieldset> already exposes role="group" named by its <legend>; we deliberately
  // do NOT add a second role="group" wrapper (it would duplicate the accessible group).
  return (
    <fieldset className="space-y-3" aria-labelledby={labelId}>
      <legend id={labelId} className="text-sm font-medium text-foreground">
        {question.prompt}
      </legend>
      <div className="space-y-2">
        {question.options.map((option) => (
          <label
            key={option.value}
            className={cn(
              "flex items-center gap-3 rounded-lg border px-4 py-2.5 cursor-pointer transition-colors",
              value.includes(option.value)
                ? "border-primary bg-primary/5"
                : "border-border hover:bg-accent",
            )}
          >
            <input
              type="checkbox"
              value={option.value}
              checked={value.includes(option.value)}
              onChange={() => toggle(option.value)}
              className="h-4 w-4 rounded accent-primary"
            />
            <span className="text-sm text-foreground">{option.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function MatrixField({
  question,
  value,
  onChange,
}: {
  question: MatrixQuestion;
  value: Record<string, string>;
  onChange: (v: Record<string, string>) => void;
}) {
  const groupLabelId = `${question.id}-label`;
  function setRow(rowValue: string, rating: string) {
    onChange({ ...value, [rowValue]: rating });
  }
  return (
    <fieldset className="space-y-3">
      <legend id={groupLabelId} className="text-sm font-medium text-foreground">
        {question.prompt}
      </legend>
      <div className="space-y-4">
        {question.rows.map((row) => {
          const rowLabelId = `${question.id}-${row.value}-label`;
          return (
            <div key={row.value} className="space-y-2">
              <p id={rowLabelId} className="text-sm font-medium text-foreground">
                {row.label}
              </p>
              <div
                role="radiogroup"
                aria-labelledby={rowLabelId}
                className="flex flex-wrap gap-2"
              >
                {question.options.map((option) => {
                  const checked = value[row.value] === option.value;
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
                        name={`${question.id}-${row.value}`}
                        value={option.value}
                        checked={checked}
                        onChange={() => setRow(row.value, option.value)}
                        className="h-4 w-4 accent-primary"
                      />
                      <span className="text-xs text-foreground">{option.label}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}
