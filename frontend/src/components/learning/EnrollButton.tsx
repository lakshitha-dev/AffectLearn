"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useEnrollMutation, useCourse } from "@/hooks/use-courses";
import { useResumeTarget, buildResumeUrl } from "@/hooks/use-progress";
import type { Enrollment } from "@/types/enrollment";

interface EnrollButtonProps {
  courseId: string;
  enrollment: Enrollment | null | undefined;
  isLoading?: boolean;
}

export function EnrollButton({
  courseId,
  enrollment,
  isLoading,
}: EnrollButtonProps) {
  const router = useRouter();
  const mutation = useEnrollMutation();
  const courseQuery = useCourse(courseId);
  const resumeQuery = useResumeTarget(enrollment ? courseId : undefined);

  function navigate() {
    if (resumeQuery.data) {
      router.push(buildResumeUrl(resumeQuery.data));
      return;
    }
    // Fall back to first lesson if resume target not loaded yet
    const course = courseQuery.data;
    const firstModule = course?.modules?.[0];
    const firstLesson = firstModule?.lessons?.[0];
    if (firstModule && firstLesson) {
      router.push(`/courses/${courseId}/modules/${firstModule.id}/lessons/${firstLesson.id}`);
    } else {
      router.push(`/courses/${courseId}`);
    }
  }

  if (isLoading) {
    return (
      <Button size="lg" disabled aria-label="Loading enrollment status">
        Loading…
      </Button>
    );
  }

  // A `dropped` enrollment is a row that still exists — that is the whole point, it holds the
  // learner's progress — but it is not active membership. Treating it as enrolled would offer
  // "Continue Learning" to someone who has left, with no way back in.
  if (enrollment && enrollment.status !== "dropped") {
    const progress = enrollment.progressPercentage;
    const isCourseComplete = resumeQuery.data?.isCourseComplete ?? false;
    const noContent = resumeQuery.isFetched && resumeQuery.data === null
      && courseQuery.data && !courseQuery.data.modules?.[0]?.lessons?.[0];

    if (noContent) {
      return (
        <Button size="lg" disabled aria-disabled="true">
          Course content coming soon
        </Button>
      );
    }

    const label = isCourseComplete
      ? "Review course"
      : progress > 0
      ? `Continue Learning · ${Math.round(progress)}%`
      : "Start Learning";

    return (
      <Button size="lg" onClick={navigate}>
        {label}
      </Button>
    );
  }

  return (
    <Button
      size="lg"
      disabled={mutation.isPending}
      onClick={() =>
        mutation.mutate(
          { courseId },
          {
            onSuccess: () => {
              toast.success("You're enrolled! Ready to start learning.");
            },
            onError: (error) => {
              toast.error(error.message || "Could not enroll. Please try again.");
            },
          },
        )
      }
    >
      {mutation.isPending ? "Enrolling…" : "Enroll"}
    </Button>
  );
}
