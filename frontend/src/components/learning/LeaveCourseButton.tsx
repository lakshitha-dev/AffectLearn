"use client";

import { useState } from "react";
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
import { useDropEnrollment } from "@/hooks/use-courses";

/**
 * Leave a course you have enrolled in.
 *
 * The wording matters and is the reason this is a dialog rather than a bare button. Leaving does
 * NOT delete anything: the enrollment is marked `dropped` and every completed section and
 * assessment score stays attached to it, so rejoining resumes where the learner stopped. Saying
 * so plainly is the difference between an action someone can take confidently and one they avoid
 * because they cannot tell what it will cost them.
 *
 * Erasure is a separate, deliberate act with its own confirmation — the export/delete controls on
 * the profile page.
 */
export function LeaveCourseButton({ courseId }: { courseId: string }) {
  const [open, setOpen] = useState(false);
  const drop = useDropEnrollment();

  async function confirm() {
    try {
      await drop.mutateAsync({ courseId });
      toast.success("You've left the course. Your progress is saved if you come back.");
      setOpen(false);
    } catch {
      toast.error("Could not leave the course. Please try again.");
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
      >
        Leave this course
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Leave this course?</DialogTitle>
            <DialogDescription>
              Your progress and any assessment scores are kept. If you enrol again later, you
              will pick up exactly where you left off.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Stay enrolled
            </Button>
            <Button onClick={confirm} disabled={drop.isPending}>
              {drop.isPending ? "Leaving…" : "Leave course"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
