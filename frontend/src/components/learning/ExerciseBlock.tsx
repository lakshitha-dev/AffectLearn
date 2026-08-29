"use client";

import { useState } from "react";
import { Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

interface ExerciseContent {
  prompt: string;
  answer: string;
  type?: "text" | "number";
  explanation?: string;
}

interface ExerciseBlockProps {
  blockId: string;
  content: ExerciseContent;
  onSubmit?: (blockId: string, answer: string, isCorrect: boolean) => void;
  /**
   * Fired when the learner reveals the answer. A learner giving up is probably the single
   * clearest confusion signal this UI produces, and until now it was discarded entirely — the
   * button only called `setInput(content.answer)` locally. Logged for future model training;
   * it does not change anything the learner sees.
   */
  onShowAnswer?: (blockId: string) => void;
  previewMode?: boolean;
}

export function ExerciseBlock({
  blockId,
  content,
  onSubmit,
  onShowAnswer,
  previewMode,
}: ExerciseBlockProps) {
  const [input, setInput] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [isCorrect, setIsCorrect] = useState(false);

  function handleSubmit() {
    const correct = input.trim().toLowerCase() === content.answer.trim().toLowerCase();
    setIsCorrect(correct);
    setSubmitted(true);
    onSubmit?.(blockId, input, correct);
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-5 space-y-4">
      <p className="font-medium text-base text-foreground">{content.prompt}</p>

      <div className="flex gap-3 items-center">
        <input
          type={content.type === "number" ? "number" : "text"}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={submitted || previewMode}
          placeholder="Your answer…"
          className={cn(
            "flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm",
            "focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary",
            (submitted || previewMode) && "cursor-default opacity-75"
          )}
          onKeyDown={(e) => {
            if (e.key === "Enter" && input.trim() && !submitted) handleSubmit();
          }}
        />
        {!submitted && !previewMode && (
          <Button size="sm" disabled={!input.trim()} onClick={handleSubmit}>
            Submit
          </Button>
        )}
      </div>

      {submitted && (
        <div className={cn("flex items-center gap-2 text-sm font-medium", isCorrect ? "text-success" : "text-destructive")}>
          {isCorrect ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />}
          {isCorrect ? "Correct!" : `The answer is: ${content.answer}`}
        </div>
      )}

      {submitted && !isCorrect && content.explanation && (
        <p className="text-sm text-muted-foreground border-t border-border pt-3">{content.explanation}</p>
      )}

      {!submitted && (
        <button
          className="text-xs text-muted-foreground hover:text-foreground underline"
          onClick={() => {
            setInput(content.answer);
            onShowAnswer?.(blockId);
          }}
          type="button"
        >
          Show answer
        </button>
      )}
    </div>
  );
}
