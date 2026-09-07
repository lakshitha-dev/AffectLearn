"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useQueryClient } from "@tanstack/react-query";

import type { SectionDetail } from "@/types/course";
import { upsertBlock } from "./upsert-block";

interface ExerciseEditorTabProps {
  /** The section chosen in the editor shell. Undefined only when the lesson has none. */
  section: SectionDetail | undefined;
  lessonId: string;
}

export function ExerciseEditorTab({ section, lessonId }: ExerciseEditorTabProps) {
  const queryClient = useQueryClient();
  const exerciseBlock = section?.contentBlocks?.find((b) => b.blockType === "exercise");
  const existing = exerciseBlock?.content as { prompt?: string; answer?: string; explanation?: string; type?: string } | undefined;

  const [prompt, setPrompt] = useState(existing?.prompt ?? "");
  const [answer, setAnswer] = useState(existing?.answer ?? "");
  const [explanation, setExplanation] = useState(existing?.explanation ?? "");
  const [type, setType] = useState<"text" | "number">(existing?.type === "number" ? "number" : "text");
  const [saving, setSaving] = useState(false);

  // Re-seed when the editor switches section. Without this the previous section's exercise stays
  // in the form and the next Save writes it into the newly-selected section.
  const [seededFor, setSeededFor] = useState<string | undefined>(section?.id);
  if (seededFor !== section?.id) {
    setSeededFor(section?.id);
    setPrompt(existing?.prompt ?? "");
    setAnswer(existing?.answer ?? "");
    setExplanation(existing?.explanation ?? "");
    setType(existing?.type === "number" ? "number" : "text");
  }

  async function handleSave() {
    if (!prompt.trim()) { toast.error("Prompt is required"); return; }
    if (!answer.trim()) { toast.error("Answer is required"); return; }
    setSaving(true);
    try {
      const content = { prompt, answer, type, explanation };
      await upsertBlock({ section, blockType: "exercise", content });
      await queryClient.invalidateQueries({ queryKey: ["lessonDetail", lessonId] });
      toast.success("Exercise saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save exercise");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5 max-w-2xl">
      <div>
        <label className="text-sm font-medium text-foreground">Exercise prompt</label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          placeholder="What is the subnet mask for a /24 network?"
          className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        />
      </div>

      <div>
        <label className="text-sm font-medium text-foreground">Correct answer</label>
        <input
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder="255.255.255.0"
          className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        />
      </div>

      <div>
        <label className="text-sm font-medium text-foreground">Answer type</label>
        <select
          value={type}
          onChange={(e) => setType(e.target.value as "text" | "number")}
          className="mt-1 rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <option value="text">Text</option>
          <option value="number">Number</option>
        </select>
      </div>

      <div>
        <label className="text-sm font-medium text-foreground">Explanation (optional)</label>
        <input
          value={explanation}
          onChange={(e) => setExplanation(e.target.value)}
          placeholder="Explain the answer…"
          className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        />
      </div>

      <Button onClick={handleSave} disabled={saving}>
        {saving ? "Saving…" : "Save exercise"}
      </Button>
    </div>
  );
}