"use client";

import { cn } from "@/lib/cn";
import type { AssessmentQuestion } from "@/types/assessment";

interface QuestionCardProps {
  question: AssessmentQuestion;
  selectedOptionId: string | undefined;
  onSelect: (questionId: string, optionId: string) => void;
  index: number;
}

export function QuestionCard({ question, selectedOptionId, onSelect, index }: QuestionCardProps) {
  return (
    <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
      <p id={`question-${question.id}`} className="font-medium text-base text-foreground">
        {index + 1}. {question.text}
      </p>
      <div
        role="radiogroup"
        aria-labelledby={`question-${question.id}`}
        className="space-y-2"
      >
        {question.options.map((option) => {
          const isSelected = selectedOptionId === option.id;
          return (
            <button
              key={option.id}
              role="radio"
              aria-checked={isSelected}
              onClick={() => onSelect(question.id, option.id)}
              className={cn(
                "w-full text-left px-4 py-3 rounded-md border transition-colors",
                "hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                isSelected
                  ? "bg-primary-soft border-primary font-medium text-foreground"
                  : "border-border text-foreground"
              )}
            >
              {option.text}
            </button>
          );
        })}
      </div>
    </div>
  );
}
