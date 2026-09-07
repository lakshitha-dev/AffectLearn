"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  useAddQuestion,
  useCreateAssessment,
  useDeleteAssessment,
  useDeleteQuestion,
  useModuleAssessments,
  useUpdateQuestion,
  type AuthoringAssessment,
  type AuthoringOption,
  type AuthoringQuestion,
} from "@/hooks/use-assessment-authoring";

interface AssessmentEditorProps {
  moduleId: string;
}

const BLANK_OPTIONS: AuthoringOption[] = [
  { text: "", isCorrect: true, sortOrder: 0 },
  { text: "", isCorrect: false, sortOrder: 1 },
];

/**
 * Author a module's pre- and post-assessments.
 *
 * FR9 gives learners a pre- and post-assessment per module, and the learner side of that has been
 * built and tested for a long time: taking one, scoring it, showing results, blocking the post
 * until the module is complete. What never existed was any way to CREATE one. The endpoints were
 * implemented and role-guarded and no interface called them, so the only route to an assessment
 * was to POST the JSON by hand — which means, in practice, that a designer could not set up the
 * measurement the study is built around.
 *
 * Exactly one pre and one post per module, because that is what the learner routes fetch
 * (`?module_id=&type=`). Offering an "add another" for a slot that can only hold one would be
 * offering a button whose result the learner side cannot show.
 */
export function AssessmentEditor({ moduleId }: AssessmentEditorProps) {
  const { data, isPending, isError } = useModuleAssessments(moduleId);
  const assessments = data ?? [];

  const pre = assessments.find((a) => a.assessmentType === "pre");
  const post = assessments.find((a) => a.assessmentType === "post");

  return (
    <section className="mt-10 rounded-lg border border-border bg-surface p-6">
      <h2 className="font-semibold text-foreground">Assessments</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        A check before the module and one after it. Learners see the post-assessment only once
        they have finished every section.
      </p>

      {isPending ? (
        <p className="mt-4 text-sm text-muted-foreground">Loading assessments…</p>
      ) : isError ? (
        <p className="mt-4 text-sm text-muted-foreground">Could not load assessments.</p>
      ) : (
        <div className="mt-5 space-y-6">
          <AssessmentSlot
            moduleId={moduleId}
            type="pre"
            label="Pre-assessment"
            blurb="Let's see where you're starting from."
            assessment={pre}
          />
          <AssessmentSlot
            moduleId={moduleId}
            type="post"
            label="Post-assessment"
            blurb="Let's see how much you've learned."
            assessment={post}
          />
        </div>
      )}
    </section>
  );
}

function AssessmentSlot({
  moduleId,
  type,
  label,
  blurb,
  assessment,
}: {
  moduleId: string;
  type: "pre" | "post";
  label: string;
  blurb: string;
  assessment: AuthoringAssessment | undefined;
}) {
  const createAssessment = useCreateAssessment(moduleId);
  const deleteAssessment = useDeleteAssessment(moduleId);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [adding, setAdding] = useState(false);

  async function create() {
    try {
      await createAssessment.mutateAsync({ assessmentType: type, title: label });
      toast.success(`${label} created`);
    } catch {
      toast.error(`Could not create the ${label.toLowerCase()}`);
    }
  }

  async function remove() {
    if (!assessment) return;
    try {
      await deleteAssessment.mutateAsync({ assessmentId: assessment.id });
      toast.success(`${label} removed`);
      setConfirmDelete(false);
    } catch {
      toast.error("Could not remove it. Please try again.");
    }
  }

  if (!assessment) {
    return (
      <div className="rounded-md border border-dashed border-border p-5">
        <p className="text-sm font-medium text-foreground">{label}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Not set up yet. Learners are shown: “{blurb}”
        </p>
        <Button
          size="sm"
          variant="outline"
          className="mt-3"
          disabled={createAssessment.isPending}
          onClick={create}
        >
          {createAssessment.isPending ? "Creating…" : `Create ${label.toLowerCase()}`}
        </Button>
      </div>
    );
  }

  const questions = [...assessment.questions].sort((a, b) => a.sortOrder - b.sortOrder);

  return (
    <div className="rounded-md border border-border p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-foreground">{label}</p>
          <p className="text-xs text-muted-foreground">
            {questions.length} {questions.length === 1 ? "question" : "questions"}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setConfirmDelete(true)}
          className="text-xs text-muted-foreground underline-offset-4 hover:text-destructive hover:underline"
        >
          Remove
        </button>
      </div>

      <ul className="mt-4 space-y-3">
        {questions.map((question) => (
          <QuestionRow key={question.id} moduleId={moduleId} question={question} />
        ))}
      </ul>

      {adding ? (
        <QuestionForm
          moduleId={moduleId}
          assessmentId={assessment.id}
          nextSortOrder={questions.length}
          onDone={() => setAdding(false)}
        />
      ) : (
        <Button
          size="sm"
          variant="outline"
          className="mt-4"
          onClick={() => setAdding(true)}
        >
          <Plus className="mr-1 h-4 w-4" /> Add question
        </Button>
      )}

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Remove this {label.toLowerCase()}?</DialogTitle>
            <DialogDescription>
              Its questions go with it, along with any scores learners have already recorded
              against them. A score against a question that no longer exists describes nothing,
              which is why they cannot be kept.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              Keep it
            </Button>
            <Button onClick={remove} disabled={deleteAssessment.isPending}>
              {deleteAssessment.isPending ? "Removing…" : "Remove"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function QuestionRow({
  moduleId,
  question,
}: {
  moduleId: string;
  question: AuthoringQuestion;
}) {
  const [editing, setEditing] = useState(false);
  const deleteQuestion = useDeleteQuestion(moduleId);

  if (editing) {
    return (
      <li>
        <QuestionForm
          moduleId={moduleId}
          question={question}
          nextSortOrder={question.sortOrder}
          onDone={() => setEditing(false)}
        />
      </li>
    );
  }

  return (
    <li className="rounded-md border border-border bg-background p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <p className="text-sm text-foreground">{question.text}</p>
          <ul className="mt-1 space-y-0.5">
            {[...question.options]
              .sort((a, b) => a.sortOrder - b.sortOrder)
              .map((option, i) => (
                <li
                  key={option.id ?? i}
                  className={
                    option.isCorrect
                      ? "text-xs font-medium text-success"
                      : "text-xs text-muted-foreground"
                  }
                >
                  {option.isCorrect ? "✓ " : "· "}
                  {option.text}
                </li>
              ))}
          </ul>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="text-xs text-primary hover:underline"
          >
            Edit
          </button>
          <button
            type="button"
            aria-label="Delete question"
            disabled={deleteQuestion.isPending}
            onClick={async () => {
              try {
                await deleteQuestion.mutateAsync({ questionId: question.id });
                toast.success("Question deleted");
              } catch {
                toast.error("Could not delete the question");
              }
            }}
            className="text-muted-foreground hover:text-destructive"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
    </li>
  );
}

function QuestionForm({
  moduleId,
  assessmentId,
  question,
  nextSortOrder,
  onDone,
}: {
  moduleId: string;
  assessmentId?: string;
  question?: AuthoringQuestion;
  nextSortOrder: number;
  onDone: () => void;
}) {
  const addQuestion = useAddQuestion(moduleId);
  const updateQuestion = useUpdateQuestion(moduleId);

  const [text, setText] = useState(question?.text ?? "");
  const [explanation, setExplanation] = useState(question?.explanation ?? "");
  const [options, setOptions] = useState<AuthoringOption[]>(
    question
      ? [...question.options].sort((a, b) => a.sortOrder - b.sortOrder)
      : BLANK_OPTIONS
  );

  const pending = addQuestion.isPending || updateQuestion.isPending;

  function setCorrect(index: number) {
    // Exactly one correct answer is enforced by the API too; keeping the radio behaviour here
    // means the form cannot be submitted into a state the server will reject.
    setOptions((prev) => prev.map((o, i) => ({ ...o, isCorrect: i === index })));
  }

  async function save() {
    const filled = options
      .filter((o) => o.text.trim())
      .map((o, i) => ({ ...o, text: o.text.trim(), sortOrder: i }));

    if (!text.trim()) {
      toast.error("Question text is required");
      return;
    }
    if (filled.length < 2) {
      toast.error("At least two options are required");
      return;
    }
    if (!filled.some((o) => o.isCorrect)) {
      toast.error("Mark one option as correct");
      return;
    }

    try {
      if (question) {
        await updateQuestion.mutateAsync({
          questionId: question.id,
          text: text.trim(),
          sortOrder: nextSortOrder,
          explanation: explanation.trim() || null,
          options: filled,
        });
      } else {
        await addQuestion.mutateAsync({
          assessmentId: assessmentId!,
          text: text.trim(),
          sortOrder: nextSortOrder,
          explanation: explanation.trim() || null,
          options: filled,
        });
      }
      toast.success(question ? "Question updated" : "Question added");
      onDone();
    } catch {
      toast.error("Could not save the question");
    }
  }

  return (
    <div className="mt-4 space-y-3 rounded-md border border-border bg-background p-4">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={2}
        placeholder="Question text…"
        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
      />

      <div className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground">
          Options — select the correct one
        </p>
        {options.map((option, index) => (
          <div key={index} className="flex items-center gap-2">
            <input
              type="radio"
              name={`correct-${question?.id ?? "new"}`}
              checked={option.isCorrect}
              onChange={() => setCorrect(index)}
              aria-label={`Option ${index + 1} is correct`}
            />
            <Input
              value={option.text}
              onChange={(e) =>
                setOptions((prev) =>
                  prev.map((o, i) => (i === index ? { ...o, text: e.target.value } : o))
                )
              }
              placeholder={`Option ${index + 1}`}
              className="h-9 flex-1"
            />
            {options.length > 2 && (
              <button
                type="button"
                aria-label={`Remove option ${index + 1}`}
                onClick={() =>
                  setOptions((prev) => prev.filter((_, i) => i !== index))
                }
                className="text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </div>
        ))}
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            setOptions((prev) => [
              ...prev,
              { text: "", isCorrect: false, sortOrder: prev.length },
            ])
          }
        >
          <Plus className="mr-1 h-4 w-4" /> Add option
        </Button>
      </div>

      <Input
        value={explanation}
        onChange={(e) => setExplanation(e.target.value)}
        placeholder="Explanation shown after a wrong answer (optional)"
        className="h-9"
      />

      <div className="flex justify-end gap-2">
        <Button size="sm" variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button size="sm" onClick={save} disabled={pending}>
          {pending ? "Saving…" : "Save question"}
        </Button>
      </div>
    </div>
  );
}
