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
  /** Fired when a quiz in this section is answered — carries the frustration/deliberation
   *  probe (correctness + time-to-answer) for behavioral-data collection. */
  onQuizAnswered?: (
    sectionId: string,
    blockId: string,
    selectedIds: string[],
    isCorrect: boolean,
    responseTimeMs: number,
  ) => void;
  /** Fired when the learner reveals an exercise answer in this section — a giving-up signal. */
  onShowAnswer?: (sectionId: string, blockId: string) => void;
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
  onQuizAnswered,
  onShowAnswer,
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

  const handleQuizSubmit = (
    blockId: string,
    selectedIds: string[],
    isCorrect: boolean,
    responseTimeMs: number,
  ) => {
    setAnsweredQuizIds((prev) => {
      if (prev.has(blockId)) return prev;
      const next = new Set(prev);
      next.add(blockId);
      return next;
    });
    onQuizAnswered?.(section.id, blockId, selectedIds, isCorrect, responseTimeMs);
  };

  return (
    <section id={`section-${section.id}`} className="scroll-mt-16 py-8">
      <h2 className="mb-6 text-2xl font-semibold text-foreground">{section.title}</h2>

      <div className="space-y-6">
        {sortedBlocks.map((block) => (
          // `data-track` names the block for the research record (hover dwell, clicks) without
          // reading its content -- see `lib/track-target.ts`.
          <div key={block.id} data-track={`block-${block.id}`}>
            <ContentBlockRenderer
              block={block}
              onQuizSubmit={handleQuizSubmit}
              onShowAnswer={(blockId) => onShowAnswer?.(section.id, blockId)}
            />
          </div>
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
              data-track="section-complete"
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
            <Button variant="outline" size="sm" onClick={onPrev} data-track="nav-prev">
              Previous
            </Button>
          )}
          {isCompleted && (
            <Button size="sm" onClick={onNext} data-track="nav-next">
              {isLast ? lastSectionCta : "Next"}
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}
