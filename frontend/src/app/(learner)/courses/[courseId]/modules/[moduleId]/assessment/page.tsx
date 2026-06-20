"use client";

import { use } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";

import { AssessmentScreen } from "@/components/learning/AssessmentScreen";
import { AssessmentResults } from "@/components/learning/AssessmentResults";
import { useAssessment, useLatestAttempt, useSubmitAttempt } from "@/hooks/use-assessments";
import { useCourse } from "@/hooks/use-courses";
import type { AnswerPayload, AttemptResult } from "@/types/assessment";
import { useState } from "react";

interface PageProps {
  params: Promise<{ courseId: string; moduleId: string }>;
}

export default function AssessmentPage({ params }: PageProps) {
  const { courseId, moduleId } = use(params);
  const searchParams = useSearchParams();
  const type = (searchParams.get("type") ?? "pre") as "pre" | "post";
  const router = useRouter();

  const assessmentQuery = useAssessment(moduleId, type);
  const latestAttemptQuery = useLatestAttempt(assessmentQuery.data?.id);
  const submitMutation = useSubmitAttempt();
  const courseQuery = useCourse(courseId);
  const [submittedResult, setSubmittedResult] = useState<AttemptResult | null>(null);

  if (assessmentQuery.isLoading || latestAttemptQuery.isLoading) {
    return <AssessmentSkeleton />;
  }

  if (!assessmentQuery.data) {
    const firstModule = courseQuery.data?.modules?.[0];
    const firstLesson = firstModule?.lessons?.[0];
    if (firstLesson) {
      router.replace("/courses/" + courseId + "/modules/" + firstModule!.id + "/lessons/" + firstLesson.id);
    } else {
      router.replace("/courses/" + courseId);
    }
    return null;
  }

  const assessment = assessmentQuery.data;

  // Already attempted pre → redirect to first lesson
  if (type === "pre" && latestAttemptQuery.data && !submittedResult) {
    const firstModule = courseQuery.data?.modules?.find((m) => m.id === moduleId);
    const firstLesson = firstModule?.lessons?.[0];
    if (firstLesson) {
      router.replace("/courses/" + courseId + "/modules/" + moduleId + "/lessons/" + firstLesson.id);
      return null;
    }
  }

  // Show results (either from previous attempt for post, or after submit)
  const resultToShow = submittedResult ?? (type === "post" ? latestAttemptQuery.data : null);
  if (resultToShow) {
    const firstModule = courseQuery.data?.modules?.find((m) => m.id === moduleId);
    const firstLesson = firstModule?.lessons?.[0];
    const firstLessonUrl = firstLesson
      ? "/courses/" + courseId + "/modules/" + moduleId + "/lessons/" + firstLesson.id
      : undefined;
    return (
      <AssessmentResults
        result={resultToShow}
        type={type}
        moduleId={moduleId}
        courseId={courseId}
        firstLessonUrl={firstLessonUrl}
      />
    );
  }

  function handleSubmit(answers: AnswerPayload[]) {
    submitMutation.mutate(
      { assessmentId: assessment.id, answers },
      {
        onSuccess: (result) => setSubmittedResult(result),
        onError: () => toast.error("Could not submit assessment. Try again."),
      }
    );
  }

  return (
    <AssessmentScreen
      assessment={assessment}
      type={type}
      onSubmit={handleSubmit}
      isSubmitting={submitMutation.isPending}
    />
  );
}

function AssessmentSkeleton() {
  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-8 py-12 animate-pulse space-y-8">
      <div className="space-y-2">
        <div className="h-8 w-3/4 bg-border rounded" />
        <div className="h-4 w-1/2 bg-border rounded" />
      </div>
      {[1, 2, 3].map((i) => (
        <div key={i} className="h-32 bg-border rounded-xl" />
      ))}
    </div>
  );
}