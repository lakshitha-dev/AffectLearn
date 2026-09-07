"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import { ContentTab } from "./ContentTab";
import { QuizEditorTab } from "./QuizEditorTab";
import { ExerciseEditorTab } from "./ExerciseEditorTab";
import { PreviewTab } from "./PreviewTab";
import type { LessonDetail } from "@/types/course";

type EditorTab = "content" | "quiz" | "exercise" | "preview";

interface LessonEditorProps {
  lesson: LessonDetail;
  courseId: string;
  moduleId: string;
  lessonId: string;
}

/**
 * The lesson editor shell: Content | Quiz | Exercise | Preview (Story 2.7).
 *
 * SECTION SELECTION
 *
 * Every tab used to read `lesson.sections[0]` directly, so on a lesson with more than one section
 * only the first was reachable — the rest were visible to learners and unreachable to their
 * author, with nothing on screen saying so. The selected section now lives here, once, and is
 * passed down, so the tabs operate on whichever section is chosen.
 *
 * The selector is hidden for single-section lessons: a picker with one option is noise.
 */
export function LessonEditor({ lesson, courseId, moduleId, lessonId }: LessonEditorProps) {
  const [activeTab, setActiveTab] = useState<EditorTab>("content");

  const sections = lesson.sections ?? [];
  const [sectionId, setSectionId] = useState<string | undefined>(sections[0]?.id);
  const section = sections.find((s) => s.id === sectionId) ?? sections[0];

  const tabs: { id: EditorTab; label: string }[] = [
    { id: "content", label: "Content" },
    { id: "quiz", label: "Quiz" },
    { id: "exercise", label: "Exercise" },
    { id: "preview", label: "Preview" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{lesson.title}</h1>
        <p className="text-sm text-muted-foreground mt-1">Editing lesson content</p>
      </div>

      {sections.length > 1 && activeTab !== "preview" && (
        <div className="flex items-center gap-3">
          <label htmlFor="editor-section" className="text-sm font-medium text-foreground">
            Section
          </label>
          <select
            id="editor-section"
            value={section?.id ?? ""}
            onChange={(e) => setSectionId(e.target.value)}
            className="h-9 rounded-md border border-border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          >
            {sections.map((s, i) => (
              <option key={s.id} value={s.id}>
                {i + 1}. {s.title}
              </option>
            ))}
          </select>
          <span className="text-xs text-muted-foreground">
            Content, Quiz and Exercise below apply to this section.
          </span>
        </div>
      )}

      {/* Tab bar */}
      <div className="border-b border-border">
        <div className="flex gap-0">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "px-6 py-3 text-sm font-medium transition-colors",
                activeTab === tab.id
                  ? "border-b-2 border-primary text-primary"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div>
        {sections.length === 0 && activeTab !== "preview" ? (
          <p className="rounded-lg border border-dashed border-border bg-surface p-6 text-sm text-muted-foreground">
            This lesson has no sections yet. Add one from the course structure page before
            authoring content — a block has to belong to a section.
          </p>
        ) : (
          <>
            {activeTab === "content" && (
              <ContentTab section={section} lessonId={lessonId} />
            )}
            {activeTab === "quiz" && <QuizEditorTab section={section} lessonId={lessonId} />}
            {activeTab === "exercise" && (
              <ExerciseEditorTab section={section} lessonId={lessonId} />
            )}
            {activeTab === "preview" && <PreviewTab lesson={lesson} />}
          </>
        )}
      </div>
    </div>
  );
}
