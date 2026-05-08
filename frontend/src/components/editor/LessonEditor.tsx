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

export function LessonEditor({ lesson, courseId, moduleId, lessonId }: LessonEditorProps) {
  const [activeTab, setActiveTab] = useState<EditorTab>("content");

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
        <p className="text-sm text-muted-foreground mt-1">
          Editing lesson content
        </p>
      </div>

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
        {activeTab === "content" && (
          <ContentTab lesson={lesson} lessonId={lessonId} />
        )}
        {activeTab === "quiz" && (
          <QuizEditorTab lesson={lesson} lessonId={lessonId} />
        )}
        {activeTab === "exercise" && (
          <ExerciseEditorTab lesson={lesson} lessonId={lessonId} />
        )}
        {activeTab === "preview" && (
          <PreviewTab lesson={lesson} />
        )}
      </div>
    </div>
  );
}