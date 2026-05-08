"use client";

import { useState } from "react";
import { Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

interface QuizOption {
  id: string;
  text: string;
  isCorrect: boolean;
}

interface QuizContent {
  question: string;
  type?: "single" | "multiple";
  options: QuizOption[];
  explanation?: string;
}

interface QuizBlockProps {
  blockId: string;
  content: QuizContent;
  onSubmit?: (blockId: string, selectedIds: string[], isCorrect: boolean) => void;
  previewMode?: boolean;
}

export function QuizBlock({ blockId, content, onSubmit, previewMode }: QuizBlockProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submitted, setSubmitted] = useState(false);
  const [isCorrect, setIsCorrect] = useState(false);
  const isMultiple = content.type === "multiple";

  function handleSelect(id: string) {
    if (submitted || previewMode) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (isMultiple) {
        if (next.has(id)) next.delete(id);
        else next.add(id);
      } else {
        next.clear();
        next.add(id);
      }
      return next;
    });
  }

  function handleSubmit() {
    const correctIds = new Set(content.options.filter((o) => o.isCorrect).map((o) => o.id));
    const selectedArray = Array.from(selected);
    const correct = selectedArray.length === correctIds.size && selectedArray.every((id) => correctIds.has(id));
    setIsCorrect(correct);
    setSubmitted(true);
    onSubmit?.(blockId, selectedArray, correct);
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-5 space-y-4">
      <p className="font-medium text-base text-foreground">{content.question}</p>

      <div role={isMultiple ? "group" : "radiogroup"} className="space-y-2">
        {content.options.map((option) => {
          const isSelected = selected.has(option.id);
          const showCorrect = submitted && option.isCorrect;
          const showWrong = submitted && isSelected && !option.isCorrect;

          return (
            <button
              key={option.id}
              role={isMultiple ? "checkbox" : "radio"}
              aria-checked={isSelected}
              onClick={() => handleSelect(option.id)}
              disabled={submitted || previewMode}
              className={cn(
                "w-full text-left px-4 py-3 rounded-md border transition-colors text-sm",
                !submitted && "hover:bg-border/40",
                isSelected && !submitted && "bg-primary-soft border-primary",
                showCorrect && "bg-green-50 dark:bg-green-950 border-green-400",
                showWrong && "bg-red-50 dark:bg-red-950 border-red-300",
                !isSelected && !showCorrect && "border-border text-foreground",
                (submitted || previewMode) && "cursor-default"
              )}
            >
              <span className="flex items-center gap-2">
                {submitted && showCorrect && <Check className="h-4 w-4 text-success shrink-0" />}
                {submitted && showWrong && <X className="h-4 w-4 text-destructive shrink-0" />}
                {option.text}
              </span>
            </button>
          );
        })}
      </div>

      {!submitted && !previewMode && (
        <Button
          size="sm"
          disabled={selected.size === 0}
          onClick={handleSubmit}
        >
          Check answer
        </Button>
      )}

      {submitted && (
        <div className={cn("flex items-center gap-2 text-sm font-medium", isCorrect ? "text-success" : "text-destructive")}>
          {isCorrect ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />}
          {isCorrect ? "Correct!" : "Not quite"}
        </div>
      )}

      {submitted && !isCorrect && content.explanation && (
        <p className="text-sm text-muted-foreground border-t border-border pt-3">{content.explanation}</p>
      )}
    </div>
  );
}