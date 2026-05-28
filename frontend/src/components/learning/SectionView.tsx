"use client";

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
  return (
    <section
      id={`section-${section.id}`}
      className="scroll-mt-16 py-12 border-b border-border last:border-b-0"
    >
      <h2 className="mb-6 text-2xl font-semibold text-foreground">{section.title}</h2>

      <div className="space-y-6">
        {section.contentBlocks
          .slice()
          .sort((a, b) => a.sortOrder - b.sortOrder)
          .map((block) => (
            <ContentBlockRenderer key={block.id} block={block} />
          ))}
      </div>

      <div className="mt-8 flex items-center gap-3">
        {isCompleted ? (
          <span className="inline-flex items-center gap-1.5 text-sm font-medium text-success">
            <Check className="h-4 w-4" />
            Completed
          </span>
        ) : (
          <Button
            onClick={() => onMarkComplete(section.id)}
            disabled={isSaving}
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
        )}

        <div className="ml-auto flex gap-2">
          {hasPrev && (
            <Button variant="outline" size="sm" onClick={onPrev}>
              Previous
            </Button>
          )}
          {isCompleted && (
            <Button size="sm" onClick={onNext}>
              {isLast ? lastSectionCta : "Next section"}
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}
