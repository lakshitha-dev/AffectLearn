"use client";

import { use, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { LessonEditor } from "@/components/editor/LessonEditor";
import { useLessonDetail } from "@/hooks/use-courses";
import { apiFetch } from "@/lib/api-client";

interface PageProps {
  params: Promise<{ courseId: string; moduleId: string; lessonId: string }>;
}

export default function LessonEditorPage({ params }: PageProps) {
  const { courseId, moduleId, lessonId } = use(params);
  const lessonQuery = useLessonDetail(lessonId);
  const [showPublishDialog, setShowPublishDialog] = useState(false);
  const [publishing, setPublishing] = useState(false);

  async function handlePublish() {
    setPublishing(true);
    try {
      await apiFetch(`/courses/${courseId}`, {
        method: "PUT",
        body: JSON.stringify({ isPublished: true }),
      });
      toast.success("Course published. Learners will see the updated content.");
      setShowPublishDialog(false);
    } catch {
      toast.error("Could not publish. Try again.");
    } finally {
      setPublishing(false);
    }
  }

  if (lessonQuery.isLoading) {
    return (
      <div className="animate-pulse space-y-4">
        <div className="h-8 w-1/2 bg-border rounded" />
        <div className="h-4 w-1/4 bg-border rounded" />
        <div className="h-80 bg-border rounded" />
      </div>
    );
  }

  if (!lessonQuery.data) {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold text-foreground">Lesson not found</h1>
        <Link href={"/courses/" + courseId} className="text-sm text-primary hover:underline">
          Back to course
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <nav className="flex items-center gap-2 text-sm text-muted-foreground">
          <Link href={"/editor/" + courseId} className="hover:text-foreground">
            {courseId}
          </Link>
          <span>/</span>
          <span className="text-foreground font-medium">{lessonQuery.data.title}</span>
        </nav>
        <Button size="sm" onClick={() => setShowPublishDialog(true)}>
          Publish
        </Button>
      </div>

      <LessonEditor
        lesson={lessonQuery.data}
        courseId={courseId}
        moduleId={moduleId}
        lessonId={lessonId}
      />

      {showPublishDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-background rounded-xl border border-border shadow-xl p-6 max-w-sm w-full space-y-4">
            <h2 className="text-lg font-semibold text-foreground">Publish changes?</h2>
            <p className="text-sm text-muted-foreground">
              Learners will see updates immediately.
            </p>
            <div className="flex gap-3 justify-end">
              <Button variant="outline" onClick={() => setShowPublishDialog(false)}>
                Cancel
              </Button>
              <Button onClick={handlePublish} disabled={publishing}>
                {publishing ? "Publishing…" : "Confirm"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}