"use client";

import Link from "next/link";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useResumeTarget, buildResumeUrl } from "@/hooks/use-progress";
import type { EnrollmentDetail } from "@/types/enrollment";

interface WelcomeBackCardProps {
  enrollment: EnrollmentDetail;
  firstName: string | null;
  onDismiss: () => void;
}

const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;

function isRecent(value: string | null | undefined): boolean {
  if (!value) return false;
  const ts = new Date(value);
  if (Number.isNaN(ts.getTime())) return false;
  return Date.now() - ts.getTime() < THIRTY_DAYS_MS;
}

export function WelcomeBackCard({ enrollment, firstName, onDismiss }: WelcomeBackCardProps) {
  const resumeQuery = useResumeTarget(enrollment.courseId);

  if (!isRecent(enrollment.lastAccessedAt)) return null;
  if (resumeQuery.isLoading) return <WelcomeBackSkeleton />;
  if (!resumeQuery.data) return null;

  const target = resumeQuery.data;
  const resumeUrl = buildResumeUrl(target);
  const heading = firstName ? `Welcome back, ${firstName}!` : "Welcome back!";
  const buttonLabel = target.isCourseComplete ? "Review course" : "Resume reading";

  return (
    <section
      aria-labelledby="welcome-back-heading"
      className="relative rounded-xl border-l-4 border-primary bg-primary-soft px-6 py-5"
    >
      <button
        onClick={onDismiss}
        aria-label="Dismiss welcome back"
        className="absolute right-4 top-4 rounded p-1 text-muted-foreground hover:bg-border transition-colors"
      >
        <X className="h-4 w-4" />
      </button>

      <h2 id="welcome-back-heading" className="text-xl font-semibold text-foreground">
        {heading}
      </h2>
      <p className="mt-1 text-base text-muted-foreground">
        You were on <span className="font-semibold text-foreground">{target.sectionTitle}</span>{" "}
        in <span className="font-semibold text-foreground">{target.courseTitle}</span>. Ready to continue?
      </p>

      <div className="mt-4">
        <Button asChild size="lg" aria-label={`${buttonLabel} ${target.courseTitle} at ${target.sectionTitle}`}>
          <Link href={resumeUrl}>{buttonLabel}</Link>
        </Button>
      </div>
    </section>
  );
}

function WelcomeBackSkeleton() {
  return (
    <div className="animate-pulse rounded-xl border-l-4 border-border bg-surface px-6 py-5 h-32" />
  );
}
