"use client";

import { use, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
        {/*
          `/courses/{id}` is the LEARNER route; a designer clicking it is bounced by AuthGuard to
          their own dashboard, so "Back to course" led anywhere but back to the course.
        */}
        <Link
          href={`/courses-editor/${courseId}`}
          className="text-sm text-primary hover:underline"
        >
          Back to course
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        {/*
          Was `/editor/{courseId}`, which is not a route — the editor only exists at the
          three-segment path — so the only breadcrumb on the page 404'd. It also printed the raw
          course UUID as its label. Both now point at the course structure page, which is the
          actual parent of a lesson editor.
        */}
        <nav className="flex items-center gap-2 text-sm text-muted-foreground">
          <Link href={`/courses-editor/${courseId}`} className="hover:text-foreground">
            Course structure
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

      <Dialog open={showPublishDialog} onOpenChange={setShowPublishDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Publish changes?</DialogTitle>
            <DialogDescription>Learners will see updates immediately.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPublishDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handlePublish} disabled={publishing}>
              {publishing ? "Publishing…" : "Confirm"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}