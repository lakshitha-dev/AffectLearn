"use client";

import { useState } from "react";
import { Plus, Trash2, CheckCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api-client";
import type { LessonDetail } from "@/types/course";

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
  lesson: LessonDetail;
  lessonId: string;
}

export function QuizEditorTab({ lesson, lessonId }: QuizEditorTabProps) {
  const [q, setQ] = useState<QuizQuestion>({
    question: "",
    options: [{ id: "1", text: "", isCorrect: false }, { id: "2", text: "", isCorrect: false }],
    explanation: "",
  });
  const [saving, setSaving] = useState(false);

  const quizBlock = lesson.sections?.[0]?.contentBlocks?.find((b) => b.blockType === "quiz");

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
      if (quizBlock) {
        await apiFetch(`/courses/content-blocks/${quizBlock.id}`, {
          method: "PUT",
          body: JSON.stringify({ content, blockType: "quiz" }),
        });
      }
      toast.success("Quiz saved");
    } catch {
      toast.error("Could not save quiz");
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