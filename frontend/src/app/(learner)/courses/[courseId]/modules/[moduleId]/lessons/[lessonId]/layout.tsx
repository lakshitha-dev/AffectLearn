"use client";

import { use } from "react";

import { CourseOutlineSidebar } from "@/components/learning/CourseOutlineSidebar";
import { WebcamIndicator } from "@/components/learning/WebcamIndicator";
import { AuthGuard } from "@/components/shared/auth-guard";
import { TopBar } from "@/components/shared/TopBar";
import { useCourse } from "@/hooks/use-courses";
import { useCourseProgress } from "@/hooks/use-progress";
import { useUiStore } from "@/stores/ui-store";

interface LayoutProps {
  children: React.ReactNode;
  params: Promise<{ courseId: string; moduleId: string; lessonId: string }>;
}

export default function LessonLayout({ children, params }: LayoutProps) {
  const { courseId, lessonId } = use(params);
  const { sidebarCollapsed, focusMode, toggleSidebar } = useUiStore();

  const courseQuery = useCourse(courseId);
  const progressQuery = useCourseProgress(courseId);

  const completedSectionIds = new Set(
    progressQuery.data?.completedSectionIds ?? [],
  );

  return (
    <AuthGuard allowedRoles={["learner"]}>
      <TopBar />
      <div className="flex min-h-[calc(100vh-3.5rem)]">
        {!focusMode && (
          <div className="relative">
            <CourseOutlineSidebar
              course={courseQuery.data ?? { id: courseId, modules: [], title: "", description: null, estimatedDurationMinutes: null, isPublished: true, createdAt: "", updatedAt: "" }}
              courseId={courseId}
              currentLessonId={lessonId}
              completedSectionIds={completedSectionIds}
              collapsed={sidebarCollapsed}
              focusMode={focusMode}
            />
            <button
              onClick={toggleSidebar}
              className="absolute -right-3 top-4 z-10 flex h-6 w-6 items-center justify-center rounded-full border border-border bg-background text-muted-foreground shadow-sm hover:bg-border"
              aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {sidebarCollapsed ? ">" : "<"}
            </button>
          </div>
        )}
        <main className="flex-1 min-w-0 bg-background">
          {children}
        </main>
      </div>
      <WebcamIndicator />
    </AuthGuard>
  );
}
