"use client";

import { cn } from "@/lib/cn";
import { QuizBlock } from "./QuizBlock";
import { ExerciseBlock } from "./ExerciseBlock";
import { MermaidDiagram } from "./MermaidDiagram";
import type { ContentBlock } from "@/types/course";

interface ContentBlockRendererProps {
  block: ContentBlock;
  onQuizSubmit?: (blockId: string, selectedIds: string[], isCorrect: boolean, responseTimeMs: number) => void;
  previewMode?: boolean;
}

type TextContent = { text?: string; html?: string };
type CodeContent = { code: string; language?: string };
type ImageContent = { url: string; alt?: string; caption?: string };
type CalloutContent = { text: string; variant?: "info" | "warning" | "tip" };

export function ContentBlockRenderer({ block, onQuizSubmit, previewMode }: ContentBlockRendererProps) {
  try {
    switch (block.blockType) {
      case "text": {
        const c = block.content as TextContent;
        if (c.text) {
          return (
            <div className="space-y-4">
              {c.text.split("\n\n").map((para, i) => (
                <p key={i} className="text-base leading-[1.75] text-foreground">
                  {para}
                </p>
              ))}
            </div>
          );
        }
        return null;
      }

      case "code": {
        const c = block.content as CodeContent;
        // Mermaid diagrams/charts are authored as code blocks with language "mermaid".
        if (c.language === "mermaid") {
          return <MermaidDiagram chart={c.code} />;
        }
        return (
          <pre className={cn("rounded-md bg-surface p-4 overflow-x-auto", c.language && `language-${c.language}`)}>
            <code className="font-mono text-sm text-foreground">{c.code}</code>
          </pre>
        );
      }

      case "image": {
        const c = block.content as ImageContent;
        return (
          <figure className="my-2">
            <img src={c.url} alt={c.alt ?? ""} className="max-w-full rounded-md" />
            {c.caption && (
              <figcaption className="mt-2 text-sm text-muted-foreground text-center">
                {c.caption}
              </figcaption>
            )}
          </figure>
        );
      }

      case "callout": {
        const c = block.content as CalloutContent;
        return (
          <div className="border-l-4 border-primary bg-primary-soft px-4 py-3 rounded-r-md">
            <p className="text-sm leading-relaxed text-foreground">{c.text}</p>
          </div>
        );
      }

      case "quiz": {
        return (
          <QuizBlock
            blockId={block.id}
            content={block.content as unknown as Parameters<typeof QuizBlock>[0]["content"]}
            onSubmit={onQuizSubmit}
            previewMode={previewMode}
          />
        );
      }

      case "exercise": {
        return (
          <ExerciseBlock
            blockId={block.id}
            content={block.content as unknown as Parameters<typeof ExerciseBlock>[0]["content"]}
            previewMode={previewMode}
          />
        );
      }

      default:
        return null;
    }
  } catch {
    return (
      <div className="rounded-md border border-border bg-surface px-4 py-3 text-sm text-muted-foreground">
        Content unavailable
      </div>
    );
  }
}
