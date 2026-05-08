"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { CheckCircle, RefreshCcw } from "lucide-react";
import { toast } from "sonner";

import { apiFetch } from "@/lib/api-client";
import { cn } from "@/lib/cn";
import type { LessonDetail } from "@/types/course";

type SaveState = "idle" | "saving" | "saved" | "error";

interface ContentTabProps {
  lesson: LessonDetail;
  lessonId: string;
}

export function ContentTab({ lesson, lessonId }: ContentTabProps) {
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const saveTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const idleTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Find first text block or use empty
  const textBlock = lesson.sections?.[0]?.contentBlocks?.find(
    (b) => b.blockType === "text"
  );
  const initialText = (textBlock?.content as { text?: string })?.text ?? "";
  const blockId = textBlock?.id;

  const editor = useEditor({
    extensions: [StarterKit],
    content: initialText ? `<p>${initialText.split("\n\n").join("</p><p>")}</p>` : "<p></p>",
    editorProps: {
      attributes: {
        class: "prose prose-base max-w-none min-h-[400px] focus:outline-none px-4 py-3 text-foreground",
        style: "font-family: Inter, sans-serif; font-size: 16px; line-height: 1.75;",
      },
    },
    onUpdate: ({ editor }) => {
      if (saveTimeout.current) clearTimeout(saveTimeout.current);
      setSaveState("saving");
      saveTimeout.current = setTimeout(() => {
        const text = editor.getText({ blockSeparator: "\n\n" });
        persistContent(text);
      }, 2000);
    },
  });

  const persistContent = useCallback(
    async (text: string) => {
      if (!blockId) {
        setSaveState("idle");
        return;
      }
      try {
        await apiFetch(`/courses/content-blocks/${blockId}`, {
          method: "PUT",
          body: JSON.stringify({ content: { text }, blockType: "text" }),
        });
        setSaveState("saved");
        if (idleTimeout.current) clearTimeout(idleTimeout.current);
        idleTimeout.current = setTimeout(() => setSaveState("idle"), 2000);
      } catch {
        setSaveState("error");
      }
    },
    [blockId]
  );

  useEffect(() => {
    return () => {
      if (saveTimeout.current) clearTimeout(saveTimeout.current);
      if (idleTimeout.current) clearTimeout(idleTimeout.current);
    };
  }, []);

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-1 rounded-lg border border-border bg-surface p-2 flex-wrap">
        {[
          { label: "H1", action: () => editor?.chain().focus().toggleHeading({ level: 1 }).run() },
          { label: "H2", action: () => editor?.chain().focus().toggleHeading({ level: 2 }).run() },
          { label: "H3", action: () => editor?.chain().focus().toggleHeading({ level: 3 }).run() },
          { label: "B", action: () => editor?.chain().focus().toggleBold().run(), bold: true },
          { label: "I", action: () => editor?.chain().focus().toggleItalic().run(), italic: true },
          { label: "</>", action: () => editor?.chain().focus().toggleCodeBlock().run() },
        ].map((btn) => (
          <button
            key={btn.label}
            onClick={btn.action}
            className="px-3 py-1.5 rounded text-sm border border-border hover:bg-border/60 text-foreground font-medium transition-colors"
            style={btn.bold ? { fontWeight: 700 } : btn.italic ? { fontStyle: "italic" } : {}}
            type="button"
          >
            {btn.label}
          </button>
        ))}

        <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
          {saveState === "saving" && <span>Saving…</span>}
          {saveState === "saved" && (
            <span className="flex items-center gap-1 text-success">
              <CheckCircle className="h-3.5 w-3.5" /> Changes saved
            </span>
          )}
          {saveState === "error" && (
            <button
              onClick={() => {
                const text = editor?.getText({ blockSeparator: "\n\n" }) ?? "";
                persistContent(text);
              }}
              className="flex items-center gap-1 text-destructive hover:underline"
            >
              <RefreshCcw className="h-3.5 w-3.5" /> Save failed — Retry
            </button>
          )}
        </div>
      </div>

      {/* Editor */}
      <div className="rounded-lg border border-border bg-background min-h-[400px]">
        <EditorContent editor={editor} />
      </div>

      {!blockId && (
        <p className="text-sm text-muted-foreground">
          No text content block found in the first section. Add a text block via the API to start editing.
        </p>
      )}
    </div>
  );
}