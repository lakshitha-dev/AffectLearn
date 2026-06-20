"use client";

import { use, useEffect, useState } from "react";
import { X } from "lucide-react";

import { CourseOutlineSidebar } from "@/components/learning/CourseOutlineSidebar";
import { WebcamIndicator } from "@/components/learning/WebcamIndicator";
import { AuthGuard } from "@/components/shared/auth-guard";
import { TopBar } from "@/components/shared/TopBar";
import { useCourse } from "@/hooks/use-courses";
import { useCourseProgress } from "@/hooks/use-progress";
import { useUiStore } from "@/stores/ui-store";
import { cn } from "@/lib/cn";

interface LayoutProps {
  children: React.ReactNode;
  params: Promise<{ courseId: string; moduleId: string; lessonId: string }>;
}

export default function LessonLayout({ children, params }: LayoutProps) {
  const { courseId, lessonId } = use(params);
  const { sidebarCollapsed, focusMode, toggleSidebar } = useUiStore();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const courseQuery = useCourse(courseId);
  const progressQuery = useCourseProgress(courseId);

  const completedSectionIds = new Set(
    progressQuery.data?.completedSectionIds ?? [],
  );

  const course = courseQuery.data ?? {
    id: courseId,
    modules: [],
    title: "",
    description: null,
    estimatedDurationMinutes: null,
    isPublished: true,
    createdAt: "",
    updatedAt: "",
  };

  // Close the mobile drawer when navigating to another lesson.
  useEffect(() => setMobileNavOpen(false), [lessonId]);

  // Close the mobile drawer on Escape.
  useEffect(() => {
    if (!mobileNavOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMobileNavOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileNavOpen]);

  return (
    <AuthGuard allowedRoles={["learner"]}>
      <TopBar onMenuClick={focusMode ? undefined : () => setMobileNavOpen(true)} />
      <div className="flex min-h-[calc(100vh-3.5rem)]">
        {!focusMode && (
          <>
            {/* Mobile drawer + backdrop (below lg) */}
            {mobileNavOpen && (
              <div
                className="fixed inset-0 top-14 z-40 bg-black/40 lg:hidden"
                onClick={() => setMobileNavOpen(false)}
                aria-hidden
              />
            )}
            <div
              className={cn(
                "fixed left-0 top-14 bottom-0 z-50 w-60 bg-surface transition-transform duration-200 lg:hidden",
                mobileNavOpen ? "translate-x-0" : "-translate-x-full"
              )}
            >
              <button
                onClick={() => setMobileNavOpen(false)}
                className="absolute right-1 top-1 z-10 rounded p-1 text-muted-foreground hover:bg-border"
                aria-label="Close course outline"
              >
                <X className="h-4 w-4" />
              </button>
              <CourseOutlineSidebar
                course={course}
                courseId={courseId}
                currentLessonId={lessonId}
                completedSectionIds={completedSectionIds}
                collapsed={false}
                focusMode={focusMode}
              />
            </div>

            {/* Desktop inline sidebar (lg+) with collapse toggle */}
            <div className="relative hidden lg:block">
              <CourseOutlineSidebar
                course={course}
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
          </>
        )}
        <main className="flex-1 min-w-0 bg-background">
          {children}
        </main>
      </div>
      <WebcamIndicator />
    </AuthGuard>
  );
}
