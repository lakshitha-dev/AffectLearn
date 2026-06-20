"use client";

import Link from "next/link";
import { Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import type { AttemptResult, QuestionResult } from "@/types/assessment";

interface AssessmentResultsProps {
  result: AttemptResult;
  type: "pre" | "post";
  moduleId: string;
  courseId: string;
  firstLessonUrl?: string;
}

export function AssessmentResults({
  result,
  type,
  moduleId,
  courseId,
  firstLessonUrl,
}: AssessmentResultsProps) {
  const sorted = [...result.questions].sort((a, b) => a.sortOrder - b.sortOrder);

  return (
    <div className="max-w-2xl mx-auto px-8 py-12 space-y-8">
      <div aria-live="polite" className="rounded-xl border border-border bg-surface p-6 text-center space-y-2">
        <p className="text-3xl font-semibold text-foreground">
          You got {result.score} out of {result.maxScore} right
        </p>
        {type === "post" && result.preScore !== null && result.preMaxScore !== null && (
          <p className="text-base text-muted-foreground">
            You started at {result.preScore}/{result.preMaxScore} and finished at {result.score}/{result.maxScore}
          </p>
        )}
      </div>

      <div className="space-y-4">
        {sorted.map((q, idx) => (
          <QuestionResultCard key={q.id} question={q} index={idx} />
        ))}
      </div>

      <div className="pt-2 flex flex-wrap gap-3">
        {type === "pre" && firstLessonUrl ? (
          <Button asChild size="lg">
            <Link href={firstLessonUrl}>Continue to module</Link>
          </Button>
        ) : (
          <>
            {/* Post-assessment is the end of the study → continue to the satisfaction survey
                (Story 6.4). Keep "See your progress" available so the learner is not trapped. */}
            <Button asChild size="lg">
              <Link href="/study/survey">Continue to survey</Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href={"/courses/" + courseId}>See your progress</Link>
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function QuestionResultCard({ question, index }: { question: QuestionResult; index: number }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
      <div className="flex items-start gap-3">
        {question.isCorrect ? (
          <Check className="h-5 w-5 mt-0.5 text-success shrink-0" />
        ) : (
          <X className="h-5 w-5 mt-0.5 text-destructive shrink-0" />
        )}
        <p className="font-medium text-base text-foreground">
          {index + 1}. {question.text}
        </p>
      </div>

      <div className="space-y-2">
        {question.options.map((option) => {
          const isSelected = question.selectedOptionId === option.id;
          const isCorrect = option.isCorrect;

          return (
            <div
              key={option.id}
              className={cn(
                "px-4 py-3 rounded-md border text-sm",
                isCorrect && "bg-green-50 dark:bg-green-950 border-green-400 dark:border-green-700 text-foreground",
                !isCorrect && isSelected && "bg-red-50 dark:bg-red-950 border-red-300 dark:border-red-800 text-foreground",
                !isCorrect && !isSelected && "border-border text-muted-foreground"
              )}
            >
              {option.text}
            </div>
          );
        })}
      </div>

      {!question.isCorrect && question.explanation && (
        <p className="text-sm text-muted-foreground border-t border-border pt-3">
          {question.explanation}
        </p>
      )}
    </div>
  );
}