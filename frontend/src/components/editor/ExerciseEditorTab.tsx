"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import type { LessonDetail } from "@/types/course";
import { upsertBlock } from "./upsert-block";

interface ExerciseEditorTabProps {
  lesson: LessonDetail;
  lessonId: string;
}

export function ExerciseEditorTab({ lesson, lessonId }: ExerciseEditorTabProps) {
  const section = lesson.sections?.[0];
  const exerciseBlock = section?.contentBlocks?.find((b) => b.blockType === "exercise");
  const existing = exerciseBlock?.content as { prompt?: string; answer?: string; explanation?: string; type?: string } | undefined;

  const [prompt, setPrompt] = useState(existing?.prompt ?? "");
  const [answer, setAnswer] = useState(existing?.answer ?? "");
  const [explanation, setExplanation] = useState(existing?.explanation ?? "");
  const [type, setType] = useState<"text" | "number">(existing?.type === "number" ? "number" : "text");
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (!prompt.trim()) { toast.error("Prompt is required"); return; }
    if (!answer.trim()) { toast.error("Answer is required"); return; }
    setSaving(true);
    try {
      const content = { prompt, answer, type, explanation };
      await upsertBlock({ section, blockType: "exercise", content });
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