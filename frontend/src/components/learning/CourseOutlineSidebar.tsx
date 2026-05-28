"use client";

import Link from "next/link";
import { Check, ChevronRight } from "lucide-react";

import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/cn";
import type { CourseDetail, Lesson, Module, Section } from "@/types/course";

interface CourseOutlineSidebarProps {
  course: CourseDetail;
  courseId: string;
  currentLessonId: string;
  currentSectionId?: string;
  completedSectionIds: Set<string>;
  collapsed: boolean;
  focusMode: boolean;
}

export function CourseOutlineSidebar({
  course,
  courseId,
  currentLessonId,
  currentSectionId,
  completedSectionIds,
  collapsed,
  focusMode,
}: CourseOutlineSidebarProps) {
  if (focusMode) return null;

  if (collapsed) {
    return (
      <aside className="shrink-0 w-12 border-r border-border bg-surface">
        <div className="flex flex-col items-center pt-4 gap-2">
          {course.modules.map((mod) => (
            <span
              key={mod.id}
              className="w-7 h-7 flex items-center justify-center text-xs font-semibold rounded bg-border text-foreground"
              title={mod.title}
            >
              {mod.title[0]}
            </span>
          ))}
        </div>
      </aside>
    );
  }

  return (
    <aside className="shrink-0 w-60 border-r border-border bg-surface">
      <ScrollArea className="h-[calc(100vh-3.5rem)]">
        <nav aria-label="Course outline" className="space-y-1 p-3">
          {course.modules.map((mod) => (
            <ModuleSection
              key={mod.id}
              module={mod}
              courseId={courseId}
              currentLessonId={currentLessonId}
              currentSectionId={currentSectionId}
              completedSectionIds={completedSectionIds}
            />
          ))}
        </nav>
      </ScrollArea>
    </aside>
  );
}

interface ModuleSectionProps {
  module: Module;
  courseId: string;
  currentLessonId: string;
  currentSectionId?: string;
  completedSectionIds: Set<string>;
}

function ModuleSection({
  module,
  courseId,
  currentLessonId,
  currentSectionId,
  completedSectionIds,
}: ModuleSectionProps) {
  return (
    <div>
      <p className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {module.title}
      </p>
      {(module.lessons ?? []).map((lesson) => (
        <LessonItem
          key={lesson.id}
          lesson={lesson}
          courseId={courseId}
          moduleId={module.id}
          isCurrentLesson={lesson.id === currentLessonId}
          currentSectionId={currentSectionId}
          completedSectionIds={completedSectionIds}
        />
      ))}
    </div>
  );
}

interface LessonItemProps {
  lesson: Lesson;
  courseId: string;
  moduleId: string;
  isCurrentLesson: boolean;
  currentSectionId?: string;
  completedSectionIds: Set<string>;
}

function LessonItem({
  lesson,
  courseId,
  moduleId,
  isCurrentLesson,
  currentSectionId,
  completedSectionIds,
}: LessonItemProps) {
  return (
    <div>
      <Link
        href={`/courses/${courseId}/modules/${moduleId}/lessons/${lesson.id}`}
        className={cn(
          "flex items-center px-4 py-2 text-sm rounded-md transition-colors hover:bg-border/50",
          isCurrentLesson
            ? "bg-primary-soft border-l-2 border-primary font-medium text-primary"
            : "text-foreground"
        )}
      >
        {lesson.title}
      </Link>
      {isCurrentLesson && (lesson.sections ?? []).map((section) => (
        <SectionItem
          key={section.id}
          section={section}
          isCurrentSection={section.id === currentSectionId}
          isCompleted={completedSectionIds.has(section.id)}
        />
      ))}
    </div>
  );
}

interface SectionItemProps {
  section: Section;
  isCurrentSection: boolean;
  isCompleted: boolean;
}

function SectionItem({ section, isCurrentSection, isCompleted }: SectionItemProps) {
  return (
    <button
      className={cn(
        "w-full flex items-center gap-2 pl-8 pr-3 py-1.5 text-xs text-left rounded-md transition-colors hover:bg-border/50",
        isCurrentSection ? "text-primary font-medium" : "text-muted-foreground"
      )}
      onClick={() => {
        const el = document.getElementById(`section-${section.id}`);
        if (el) {
          el.scrollIntoView({ behavior: "smooth" });
          history.replaceState(null, "", `#section-${section.id}`);
        }
      }}
      aria-label={`${section.title}${isCompleted ? ", completed" : ""}`}
    >
      {isCompleted ? (
        <Check className="h-3 w-3 text-success shrink-0" aria-hidden="true" />
      ) : (
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full shrink-0",
            isCurrentSection ? "bg-primary" : "bg-border"
          )}
          aria-hidden="true"
        />
      )}
      <span className="truncate">{section.title}</span>
      {isCompleted && <span className="sr-only">completed</span>}
    </button>
  );
}
