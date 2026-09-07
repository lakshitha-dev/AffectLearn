"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { SectionDetail } from "@/types/course";
import { upsertBlock } from "./upsert-block";
import { parseTable, serialiseTable } from "./table-text";

interface RichBlocksEditorProps {
  section: SectionDetail | undefined;
  lessonId: string;
}

/**
 * Authoring for the block types the rich-text editor cannot express: image, table and callout.
 *
 * These three were renderable and unauthorable. `ContentBlockRenderer` has always drawn them for
 * learners, and `SectionBlocks` listed them read-only saying "the specialised tabs own these" —
 * but the Quiz and Exercise tabs are the only specialised tabs there are. A designer who wanted a
 * comparison table had to POST it to `/courses/sections/{id}/content-blocks` by hand, which is
 * not a workflow so much as the absence of one.
 *
 * TABLES ARE EDITED AS TEXT
 *
 * A pipe-delimited grid rather than a spreadsheet widget. The stored shape is
 * `{ headers: string[], rows: string[][] }`, which round-trips through a few lines of parsing;
 * a drag-resizable grid would be a large component for a block type a lesson uses once or twice.
 * `TableBlock` already tolerates ragged rows, so a typo degrades to a padded cell rather than a
 * broken table.
 */
export function RichBlocksEditor({ section, lessonId }: RichBlocksEditorProps) {
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState<string | null>(null);

  const imageBlock = section?.contentBlocks?.find((b) => b.blockType === "image");
  const tableBlock = section?.contentBlocks?.find((b) => b.blockType === "table");
  const calloutBlock = section?.contentBlocks?.find((b) => b.blockType === "callout");

  const image = imageBlock?.content as
    | { url?: string; alt?: string; caption?: string }
    | undefined;
  const table = tableBlock?.content as
    | { headers?: string[]; rows?: string[][] }
    | undefined;
  const callout = calloutBlock?.content as { text?: string } | undefined;

  const [imageUrl, setImageUrl] = useState(image?.url ?? "");
  const [imageAlt, setImageAlt] = useState(image?.alt ?? "");
  const [imageCaption, setImageCaption] = useState(image?.caption ?? "");
  const [tableText, setTableText] = useState(() => serialiseTable(table));
  const [calloutText, setCalloutText] = useState(callout?.text ?? "");

  // Re-seed on section change, for the same reason the other tabs do: otherwise the previous
  // section's blocks sit in the form waiting to be saved into the new one.
  const [seededFor, setSeededFor] = useState<string | undefined>(section?.id);
  if (seededFor !== section?.id) {
    setSeededFor(section?.id);
    setImageUrl(image?.url ?? "");
    setImageAlt(image?.alt ?? "");
    setImageCaption(image?.caption ?? "");
    setTableText(serialiseTable(table));
    setCalloutText(callout?.text ?? "");
  }

  async function save(
    kind: "image" | "table" | "callout",
    content: Record<string, unknown>
  ) {
    setSaving(kind);
    try {
      await upsertBlock({ section, blockType: kind, content });
      await queryClient.invalidateQueries({ queryKey: ["lessonDetail", lessonId] });
      toast.success(`${kind[0].toUpperCase()}${kind.slice(1)} saved`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `Could not save the ${kind}`);
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="space-y-6 border-t border-border pt-8">
      <div>
        <h2 className="font-semibold text-foreground">Other blocks</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          One of each per section. Leave a block empty to skip it.
        </p>
      </div>

      {/* --- Image --- */}
      <section className="rounded-lg border border-border bg-surface p-5">
        <h3 className="text-sm font-semibold text-foreground">Image</h3>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="blockImageUrl">Image URL</Label>
            <Input
              id="blockImageUrl"
              value={imageUrl}
              onChange={(e) => setImageUrl(e.target.value)}
              placeholder="https://…"
              className="h-10"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="blockImageAlt">Alt text</Label>
            <Input
              id="blockImageAlt"
              value={imageAlt}
              onChange={(e) => setImageAlt(e.target.value)}
              placeholder="What the image shows"
              className="h-10"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="blockImageCaption">Caption (optional)</Label>
            <Input
              id="blockImageCaption"
              value={imageCaption}
              onChange={(e) => setImageCaption(e.target.value)}
              className="h-10"
            />
          </div>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Alt text is read aloud to screen-reader users in place of the image. Describe what it
          conveys, not that it is a picture.
        </p>
        <div className="mt-4 flex justify-end">
          <Button
            size="sm"
            disabled={saving !== null || !imageUrl.trim()}
            onClick={() =>
              save("image", { url: imageUrl.trim(), alt: imageAlt, caption: imageCaption })
            }
          >
            {saving === "image" ? "Saving…" : "Save image"}
          </Button>
        </div>
      </section>

      {/* --- Table --- */}
      <section className="rounded-lg border border-border bg-surface p-5">
        <h3 className="text-sm font-semibold text-foreground">Table</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          One row per line, cells separated by <code className="font-mono">|</code>. The first
          line is the header row.
        </p>
        <textarea
          value={tableText}
          onChange={(e) => setTableText(e.target.value)}
          rows={6}
          placeholder={"Protocol | Port | Reliable\nTCP | 6 | Yes\nUDP | 17 | No"}
          className="mt-3 w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        />
        <div className="mt-4 flex justify-end">
          <Button
            size="sm"
            disabled={saving !== null || !tableText.trim()}
            onClick={() => save("table", { ...parseTable(tableText) })}
          >
            {saving === "table" ? "Saving…" : "Save table"}
          </Button>
        </div>
      </section>

      {/* --- Callout --- */}
      <section className="rounded-lg border border-border bg-surface p-5">
        <h3 className="text-sm font-semibold text-foreground">Callout</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          A short highlighted aside — a warning, a tip, or something worth not missing.
        </p>
        <textarea
          value={calloutText}
          onChange={(e) => setCalloutText(e.target.value)}
          rows={3}
          className="mt-3 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        />
        <div className="mt-4 flex justify-end">
          <Button
            size="sm"
            disabled={saving !== null || !calloutText.trim()}
            onClick={() => save("callout", { text: calloutText.trim() })}
          >
            {saving === "callout" ? "Saving…" : "Save callout"}
          </Button>
        </div>
      </section>
    </div>
  );
}
