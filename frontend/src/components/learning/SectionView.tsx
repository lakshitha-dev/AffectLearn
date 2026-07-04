"use client";

import { useMemo, useState } from "react";
import { Check, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ContentBlockRenderer } from "./ContentBlockRenderer";
import type { SectionDetail } from "@/types/course";

interface SectionViewProps {
  section: SectionDetail;
  isCompleted: boolean;
  isLast: boolean;
  hasPrev: boolean;
  lastSectionCta?: string;
  onMarkComplete: (sectionId: string) => void;
  onNext: () => void;
  onPrev: () => void;
  isSaving?: boolean;
}

export function SectionView({
  section,
  isCompleted,
  isLast,
  hasPrev,
  lastSectionCta = "Next lesson",
  onMarkComplete,
  onNext,
  onPrev,
  isSaving,
}: SectionViewProps) {
  const sortedBlocks = useMemo(
    () => section.contentBlocks.slice().sort((a, b) => a.sortOrder - b.sortOrder),
    [section.contentBlocks],
  );

  // Quiz gating: any quiz in this section must be answered before the learner can
  // mark the section complete and move on. Sections with no quiz are unaffected
  // (`every` over an empty list is true).
  const quizBlockIds = useMemo(
    () => sortedBlocks.filter((b) => b.blockType === "quiz").map((b) => b.id),
    [sortedBlocks],
  );
  const [answeredQuizIds, setAnsweredQuizIds] = useState<Set<string>>(new Set());
  const allQuizzesAnswered = quizBlockIds.every((id) => answeredQuizIds.has(id));

  const handleQuizSubmit = (blockId: string) => {
    setAnsweredQuizIds((prev) => {
      if (prev.has(blockId)) return prev;
      const next = new Set(prev);
      next.add(blockId);
      return next;
    });
  };

  return (
    <section id={`section-${section.id}`} className="scroll-mt-16 py-8">
      <h2 className="mb-6 text-2xl font-semibold text-foreground">{section.title}</h2>

      <div className="space-y-6">
        {sortedBlocks.map((block) => (
          <ContentBlockRenderer key={block.id} block={block} onQuizSubmit={handleQuizSubmit} />
        ))}
      </div>

      <div className="mt-10 flex items-center gap-3 border-t border-border pt-6">
        {isCompleted ? (
          <span className="inline-flex items-center gap-1.5 text-sm font-medium text-success">
            <Check className="h-4 w-4" />
            Completed
          </span>
        ) : (
          <div className="flex flex-col gap-1.5">
            <Button
              onClick={() => onMarkComplete(section.id)}
              disabled={isSaving || !allQuizzesAnswered}
              aria-label={`Mark section ${section.title} as complete`}
            >
              {isSaving ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Saving…
                </>
              ) : (
                "Mark complete"
              )}
            </Button>
            {!allQuizzesAnswered && (
              <p className="text-xs text-muted-foreground">
                Answer the question{quizBlockIds.length > 1 ? "s" : ""} above to continue.
              </p>
            )}
          </div>
        )}

        <div className="ml-auto flex gap-2">
          {hasPrev && (
            <Button variant="outline" size="sm" onClick={onPrev}>
              Previous
            </Button>
          )}
          {isCompleted && (
            <Button size="sm" onClick={onNext}>
              {isLast ? lastSectionCta : "Next"}
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}
