"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { QuestionCard } from "./QuestionCard";
import type { AnswerPayload, Assessment } from "@/types/assessment";

interface AssessmentScreenProps {
  assessment: Assessment;
  type: "pre" | "post";
  onSubmit: (answers: AnswerPayload[]) => void;
  isSubmitting: boolean;
}

export function AssessmentScreen({ assessment, type, onSubmit, isSubmitting }: AssessmentScreenProps) {
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const sorted = [...assessment.questions].sort((a, b) => a.sortOrder - b.sortOrder);
  const answered = Object.keys(answers).length;
  const allAnswered = answered === sorted.length;

  function handleSelect(questionId: string, optionId: string) {
    setAnswers((prev) => ({ ...prev, [questionId]: optionId }));
  }

  function handleSubmit() {
    const payload: AnswerPayload[] = Object.entries(answers).map(([questionId, selectedOptionId]) => ({
      questionId,
      selectedOptionId,
    }));
    onSubmit(payload);
  }

  const heading = type === "pre"
    ? "Let's see where you're starting from"
    : "Let's see how much you've learned";
  const subtext = type === "pre"
    ? "This isn't graded — it just helps us understand where you're starting"
    : "Answer all questions to see your results";

  return (
    <div className="max-w-2xl mx-auto px-8 py-12 space-y-8">
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold text-foreground">{heading}</h1>
        <p className="text-base text-muted-foreground">{subtext}</p>
        <p className="text-sm text-muted-foreground">
          {answered} of {sorted.length} answered
        </p>
      </div>

      <div className="space-y-4" aria-live="polite">
        {sorted.map((q, idx) => (
          <QuestionCard
            key={q.id}
            question={q}
            selectedOptionId={answers[q.id]}
            onSelect={handleSelect}
            index={idx}
          />
        ))}
      </div>

      <div className="pt-4">
        <Button
          size="lg"
          disabled={!allAnswered || isSubmitting}
          aria-disabled={!allAnswered || isSubmitting}
          onClick={handleSubmit}
        >
          {isSubmitting ? "Submitting…" : allAnswered ? "Submit assessment" : "Answer all questions to continue"}
        </Button>
      </div>
    </div>
  );
}