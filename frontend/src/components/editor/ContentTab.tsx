"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { CheckCircle, RefreshCcw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import type { ContentBlock, SectionDetail } from "@/types/course";
import { upsertBlock } from "./upsert-block";
import { RichBlocksEditor } from "./RichBlocksEditor";
import { VariantsEditor } from "./VariantsEditor";

type SaveState = "idle" | "saving" | "saved" | "error";

interface ContentTabProps {
  /** The section chosen in the editor shell. Undefined only when the lesson has none. */
  section: SectionDetail | undefined;
  lessonId: string;
}

/**
 * Prose for the selected section, plus the block types the rich-text editor cannot express.
 *
 * Two things changed here. The editor used to read `lesson.sections[0]` regardless of which
 * section was being edited; and when a section had no text block yet it set the save state back
 * to "idle" and wrote nothing — an autosave editor that silently discarded everything typed into
 * it, with a note underneath telling the author to add a text block "via the API".
 */
export function ContentTab({ section, lessonId }: ContentTabProps) {
  const queryClient = useQueryClient();
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const saveTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const idleTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const textBlock = section?.contentBlocks?.find((b) => b.blockType === "text");
  const initialText = (textBlock?.content as { text?: string })?.text ?? "";

  // Once autosave has CREATED a block, later saves must update that same block. The `section`
  // prop only refreshes after the query invalidation lands, so the new id is held here to bridge
  // the gap — otherwise a second keystroke creates a duplicate text block.
  const createdBlockId = useRef<string | null>(null);

  const asHtml = (text: string) =>
    text ? `<p>${text.split("\n\n").join("</p><p>")}</p>` : "<p></p>";

  const persistContent = useCallback(
    async (text: string) => {
      if (!section) {
        setSaveState("error");
        return;
      }
      try {
        const hasStoredTextBlock = section.contentBlocks?.some((b) => b.blockType === "text");
        const target: SectionDetail =
          createdBlockId.current && !hasStoredTextBlock
            ? {
                ...section,
                contentBlocks: [
                  ...(section.contentBlocks ?? []),
                  {
                    id: createdBlockId.current,
                    blockType: "text",
                    content: {},
                    sortOrder: 0,
                    variantKey: "original",
                  } as ContentBlock,
                ],
              }
            : section;

        const saved = await upsertBlock({
          section: target,
          blockType: "text",
          content: { text },
        });
        createdBlockId.current = saved.id;
        setSaveState("saved");
        await queryClient.invalidateQueries({ queryKey: ["lessonDetail", lessonId] });
        if (idleTimeout.current) clearTimeout(idleTimeout.current);
        idleTimeout.current = setTimeout(() => setSaveState("idle"), 2000);
      } catch {
        setSaveState("error");
      }
    },
    [section, queryClient, lessonId]
  );

  const editor = useEditor({
    extensions: [StarterKit],
    content: asHtml(initialText),
    editorProps: {
      attributes: {
        class:
          "prose prose-base max-w-none min-h-[400px] focus:outline-none px-4 py-3 text-foreground",
        style: "font-family: Inter, sans-serif; font-size: 16px; line-height: 1.75;",
      },
    },
    onUpdate: ({ editor }) => {
      if (saveTimeout.current) clearTimeout(saveTimeout.current);
      setSaveState("saving");
      saveTimeout.current = setTimeout(() => {
        persistContent(editor.getText({ blockSeparator: "\n\n" }));
      }, 2000);
    },
  });

  // Reload the prose when the editor switches section, so the previous section's text is not left
  // on screen where the next autosave would write it into the wrong place.
  const [seededFor, setSeededFor] = useState<string | undefined>(section?.id);
  useEffect(() => {
    if (seededFor === section?.id || !editor) return;
    setSeededFor(section?.id);
    createdBlockId.current = null;
    if (saveTimeout.current) clearTimeout(saveTimeout.current);
    setSaveState("idle");
    editor.commands.setContent(asHtml(initialText));
    // `asHtml` is a pure local formatter and intentionally not a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section?.id, seededFor, editor, initialText]);

  useEffect(() => {
    return () => {
      if (saveTimeout.current) clearTimeout(saveTimeout.current);
      if (idleTimeout.current) clearTimeout(idleTimeout.current);
    };
  }, []);

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        {/* Toolbar */}
        <div className="flex flex-wrap items-center gap-1 rounded-lg border border-border bg-surface p-2">
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
              className="rounded border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-border/60"
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
                onClick={() => persistContent(editor?.getText({ blockSeparator: "\n\n" }) ?? "")}
                className="flex items-center gap-1 text-destructive hover:underline"
              >
                <RefreshCcw className="h-3.5 w-3.5" /> Save failed — Retry
              </button>
            )}
          </div>
        </div>

        <div className="min-h-[400px] rounded-lg border border-border bg-background">
          <EditorContent editor={editor} />
        </div>
      </div>

      {/*
        Images, tables and callouts. `SectionBlocks` renders these read-only on the grounds that
        "the specialised tabs own these" — but no tab owned `table` or `image`, so both were
        renderable to learners and unauthorable by anyone short of calling the API by hand. This
        is the tab that owns them.
      */}
      <RichBlocksEditor section={section} lessonId={lessonId} />

      {/*
        The adaptive alternatives (FR19 / FR21). Placed last because a variant is an
        alternative to the prose above it, and reads oddly before the thing it replaces.
      */}
      <VariantsEditor section={section} lessonId={lessonId} />
    </div>
  );
}
