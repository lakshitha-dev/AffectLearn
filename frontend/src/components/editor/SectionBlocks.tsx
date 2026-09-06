"use client";

import { useState } from "react";

import {
  nextSortOrder,
  swapOrder,
  useCreateContentBlock,
  useDeleteContentBlock,
  useUpdateContentBlock,
} from "@/hooks/use-authoring";
import type { ContentBlock, Section } from "@/types/course";

/**
 * Add, edit, reorder and delete the content blocks inside one section.
 *
 * WHY THIS IS NEEDED SEPARATELY FROM THE LESSON EDITOR
 *
 * `ContentTab` edits `lesson.sections[0].contentBlocks.find(b => b.blockType === "text")` — the
 * FIRST text block of the FIRST section. That works for the seeded courses, which were built by
 * a script that produced exactly that shape. It cannot create a block, cannot reach a second
 * section, and cannot see a section's other blocks.
 *
 * With the structure builder able to create sections, that limitation became a dead end: a
 * newly created section has no blocks at all, so the rich editor's `.find()` returns undefined
 * and there is nothing to type into. This is what fills a new section.
 *
 * WHAT IT EDITS AND WHAT IT DELEGATES
 *
 * Prose-shaped blocks — text, code, callout — are edited here, because they are a single field
 * and a textarea is the right tool. Quiz and exercise blocks have structured content with
 * correctness semantics, and the lesson editor already has purpose-built tabs for them, so they
 * are listed read-only here with a pointer rather than given a second, worse editor.
 */

const AUTHORABLE: ReadonlyArray<{ type: ContentBlock["blockType"]; label: string; hint: string }> = [
  { type: "text", label: "Text", hint: "A paragraph of explanation." },
  { type: "code", label: "Code", hint: "A code sample." },
  { type: "callout", label: "Callout", hint: "A highlighted note or warning." },
];

/** Block types with structured content the specialised tabs own. */
const DELEGATED = new Set<ContentBlock["blockType"]>(["quiz", "exercise", "table", "image"]);

/** The single editable field for each prose-shaped type, and the key it lives under. */
function primaryField(block: ContentBlock): { key: string; value: string } | null {
  const content = block.content ?? {};
  if (block.blockType === "text" || block.blockType === "callout") {
    return { key: "text", value: String(content.text ?? "") };
  }
  if (block.blockType === "code") {
    return { key: "code", value: String(content.code ?? "") };
  }
  return null;
}

function newBlockContent(type: ContentBlock["blockType"]): Record<string, unknown> {
  if (type === "code") return { language: "text", code: "" };
  if (type === "callout") return { variant: "info", text: "" };
  return { text: "" };
}

export function SectionBlocks({
  section,
  editable,
}: {
  section: Section;
  editable: boolean;
}) {
  const createBlock = useCreateContentBlock();
  const updateBlock = useUpdateContentBlock();
  const deleteBlock = useDeleteContentBlock();

  const blocks = [...(section.contentBlocks ?? [])].sort((a, b) => a.sortOrder - b.sortOrder);

  return (
    <div>
      {blocks.length === 0 && (
        <p className="mb-3 rounded-md border border-dashed border-border px-3 py-4 text-center text-sm text-muted-foreground">
          This section is empty. Add a block to give learners something to read.
        </p>
      )}

      <ol className="space-y-2">
        {blocks.map((block, index) => (
          <BlockRow
            key={block.id}
            block={block}
            index={index}
            siblings={blocks}
            editable={editable}
            onSave={(content) =>
              updateBlock.mutateAsync({ blockId: block.id, patch: { content } })
            }
            onMove={(dir) =>
              swapOrder(blocks, block, blocks[index + dir], (id, sortOrder) =>
                updateBlock.mutateAsync({ blockId: id, patch: { sortOrder } }),
              )
            }
            onDelete={() => deleteBlock.mutateAsync(block.id)}
          />
        ))}
      </ol>

      {editable && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Add:</span>
          {AUTHORABLE.map(({ type, label, hint }) => (
            <button
              key={type}
              type="button"
              title={hint}
              disabled={createBlock.isPending}
              onClick={() =>
                createBlock.mutate({
                  sectionId: section.id,
                  blockType: type,
                  content: newBlockContent(type),
                  sortOrder: nextSortOrder(blocks),
                })
              }
              className="rounded-md border border-border px-2.5 py-1 text-xs font-medium text-foreground disabled:opacity-50"
            >
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function BlockRow({
  block,
  index,
  siblings,
  editable,
  onSave,
  onMove,
  onDelete,
}: {
  block: ContentBlock;
  index: number;
  siblings: ContentBlock[];
  editable: boolean;
  onSave: (content: Record<string, unknown>) => Promise<unknown>;
  onMove: (direction: -1 | 1) => Promise<void>;
  onDelete: () => Promise<unknown>;
}) {
  const field = primaryField(block);
  const [draft, setDraft] = useState(field?.value ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const delegated = DELEGATED.has(block.blockType);
  const dirty = field !== null && draft !== field.value;

  async function save() {
    if (!field) return;
    setSaving(true);
    setSaved(false);
    try {
      await onSave({ ...(block.content ?? {}), [field.key]: draft });
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className="rounded-md border border-border bg-background p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide text-slate-600 dark:bg-slate-800 dark:text-slate-400">
          {block.blockType}
        </span>
        {saved && !dirty && <span className="text-[11px] text-green-700">Saved</span>}
        <span className="flex-1" />
        {editable && (
          <>
            <button
              type="button"
              aria-label="Move block up"
              disabled={index === 0}
              onClick={() => void onMove(-1)}
              className="rounded px-1.5 text-xs text-muted-foreground hover:text-foreground disabled:opacity-30"
            >
              ↑
            </button>
            <button
              type="button"
              aria-label="Move block down"
              disabled={index === siblings.length - 1}
              onClick={() => void onMove(1)}
              className="rounded px-1.5 text-xs text-muted-foreground hover:text-foreground disabled:opacity-30"
            >
              ↓
            </button>
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="rounded px-1.5 text-xs text-red-700 hover:underline dark:text-red-400"
            >
              Delete
            </button>
          </>
        )}
      </div>

      {confirming && (
        <div className="mb-2 flex items-center gap-2 rounded border border-red-200 bg-red-50 px-2.5 py-2 dark:border-red-800/40 dark:bg-red-900/10">
          <span className="flex-1 text-xs text-red-800 dark:text-red-300">
            Delete this block?
          </span>
          <button
            type="button"
            onClick={() => void onDelete()}
            className="rounded bg-red-600 px-2 py-1 text-xs font-medium text-white"
          >
            Delete
          </button>
          <button
            type="button"
            onClick={() => setConfirming(false)}
            className="rounded px-2 py-1 text-xs text-muted-foreground"
          >
            Cancel
          </button>
        </div>
      )}

      {delegated ? (
        <p className="text-xs text-muted-foreground">
          {block.blockType === "quiz" || block.blockType === "exercise"
            ? "Edited on the lesson's Quiz and Exercise tabs, which understand its structure."
            : "This block type is authored elsewhere."}
        </p>
      ) : field ? (
        <>
          <textarea
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setSaved(false);
            }}
            readOnly={!editable}
            rows={block.blockType === "code" ? 6 : 3}
            className={`w-full rounded border border-border bg-surface px-2.5 py-2 text-sm ${
              block.blockType === "code" ? "font-mono text-[13px]" : ""
            }`}
          />
          {editable && (
            <div className="mt-2 flex items-center gap-2">
              <button
                type="button"
                onClick={save}
                disabled={!dirty || saving}
                className="rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save"}
              </button>
              {dirty && (
                <button
                  type="button"
                  onClick={() => setDraft(field.value)}
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  Discard
                </button>
              )}
            </div>
          )}
        </>
      ) : (
        <p className="text-xs text-muted-foreground">No editable field for this block type.</p>
      )}
    </li>
  );
}
