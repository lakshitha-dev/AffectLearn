"use client";

import { useState } from "react";
import { Plus, Trash2, CheckCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useQueryClient } from "@tanstack/react-query";

import type { SectionDetail } from "@/types/course";
import { upsertBlock } from "./upsert-block";

interface QuizOption {
  id: string;
  text: string;
  isCorrect: boolean;
}

interface QuizQuestion {
  question: string;
  options: QuizOption[];
  explanation: string;
}

interface QuizEditorTabProps {
  /** The section chosen in the editor shell. Undefined only when the lesson has none. */
  section: SectionDetail | undefined;
  lessonId: string;
}

const EMPTY_QUESTION: QuizQuestion = {
  question: "",
  options: [
    { id: "1", text: "", isCorrect: false },
    { id: "2", text: "", isCorrect: false },
  ],
  explanation: "",
};

/** Read a stored quiz block back into editor state, tolerating a partially-formed block. */
function questionFromBlock(content: unknown): QuizQuestion {
  const stored = content as
    | { question?: string; options?: QuizOption[]; explanation?: string }
    | undefined;
  if (!stored?.question && !stored?.options?.length) return EMPTY_QUESTION;
  return {
    question: stored.question ?? "",
    options:
      stored.options?.length && stored.options.length >= 2
        ? stored.options.map((o, i) => ({
            id: o.id ?? String(i + 1),
            text: o.text ?? "",
            isCorrect: Boolean(o.isCorrect),
          }))
        : EMPTY_QUESTION.options,
    explanation: stored.explanation ?? "",
  };
}

export function QuizEditorTab({ section, lessonId }: QuizEditorTabProps) {
  const queryClient = useQueryClient();
  const quizBlock = section?.contentBlocks?.find((b) => b.blockType === "quiz");

  // Seed from the stored block. Starting blank meant opening the tab on an existing quiz and
  // saving silently replaced it with an empty question.
  // Keyed on the block so switching sections re-seeds the form from THAT section's quiz rather
  // than leaving the previous section's question on screen ready to be saved into the new one.
  const [q, setQ] = useState<QuizQuestion>(() => questionFromBlock(quizBlock?.content));
  const [seededFor, setSeededFor] = useState<string | undefined>(section?.id);
  if (seededFor !== section?.id) {
    setSeededFor(section?.id);
    setQ(questionFromBlock(quizBlock?.content));
  }
  const [saving, setSaving] = useState(false);

  function addOption() {
    setQ((prev) => ({ ...prev, options: [...prev.options, { id: Date.now().toString(), text: "", isCorrect: false }] }));
  }

  function removeOption(oIdx: number) {
    setQ((prev) => ({ ...prev, options: prev.options.filter((_, i) => i !== oIdx) }));
  }

  function setCorrect(oIdx: number) {
    setQ((prev) => ({ ...prev, options: prev.options.map((o, i) => ({ ...o, isCorrect: i === oIdx })) }));
  }

  async function handleSave() {
    if (!q.question.trim()) { toast.error("Question text is required"); return; }
    const validOptions = q.options.filter((o) => o.text.trim());
    if (validOptions.length < 2) { toast.error("At least 2 options required"); return; }
    if (!validOptions.some((o) => o.isCorrect)) { toast.error("Mark one option as correct"); return; }

    setSaving(true);
    try {
      const content = {
        question: q.question,
        type: "single",
        options: validOptions.map((o) => ({ id: o.id, text: o.text, isCorrect: o.isCorrect })),
        explanation: q.explanation,
      };
      await upsertBlock({ section, blockType: "quiz", content });
      // The lesson payload now has a block it did not have before; without this the next save
      // would create a SECOND quiz block instead of updating the one just written.
      await queryClient.invalidateQueries({ queryKey: ["lessonDetail", lessonId] });
      toast.success("Quiz saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save quiz");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="space-y-3">
        <div>
          <label className="text-sm font-medium text-foreground">Question text</label>
          <textarea
            value={q.question}
            onChange={(e) => setQ((prev) => ({ ...prev, question: e.target.value }))}
            rows={2}
            placeholder="Enter your question…"
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium text-foreground">Options (check the correct answer)</p>
          {q.options.map((opt, oIdx) => (
            <div key={opt.id} className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setCorrect(oIdx)}
                className={`h-5 w-5 shrink-0 rounded-full border-2 transition-colors ${opt.isCorrect ? "border-primary bg-primary" : "border-border"}`}
                aria-label={opt.isCorrect ? "Correct answer" : "Mark as correct"}
              >
                {opt.isCorrect && <CheckCircle className="h-4 w-4 text-primary-foreground" />}
              </button>
              <input
                value={opt.text}
                onChange={(e) => {
                  const updated = q.options.map((o, i) => i === oIdx ? { ...o, text: e.target.value } : o);
                  setQ((prev) => ({ ...prev, options: updated }));
                }}
                placeholder={`Option ${oIdx + 1}`}
                className="flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              {q.options.length > 2 && (
                <button onClick={() => removeOption(oIdx)} className="text-muted-foreground hover:text-destructive">
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
          ))}
          <Button variant="outline" size="sm" onClick={() => addOption()}>
            <Plus className="h-4 w-4 mr-1" /> Add option
          </Button>
        </div>

        <div>
          <label className="text-sm font-medium text-foreground">Explanation (shown on wrong answer)</label>
          <input
            value={q.explanation}
            onChange={(e) => setQ((prev) => ({ ...prev, explanation: e.target.value }))}
            placeholder="Explain why the correct answer is correct…"
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
      </div>

      <Button onClick={handleSave} disabled={saving}>
        {saving ? "Saving…" : "Save quiz"}
      </Button>
    </div>
  );
}