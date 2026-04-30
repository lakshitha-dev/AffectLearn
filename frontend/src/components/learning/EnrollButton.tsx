"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useEnrollMutation } from "@/hooks/use-courses";
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

  if (isLoading) {
    return (
      <Button size="lg" disabled aria-label="Loading enrollment status">
        Loading…
      </Button>
    );
  }

  if (enrollment) {
    const hasProgress = enrollment.progressPercentage > 0;
    return (
      <Button
        size="lg"
        onClick={() => router.push(`/courses/${courseId}/learn`)}
      >
        {hasProgress
          ? `Continue Learning · ${Math.round(enrollment.progressPercentage)}%`
          : "Start Learning"}
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
