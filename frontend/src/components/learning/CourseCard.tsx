"use client";

import Link from "next/link";

import { cn } from "@/lib/cn";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Course } from "@/types/course";

interface CourseCardProps {
  course: Course;
  variant?: "browse" | "enrolled";
  progress?: number;
  lastAccessedAt?: string | null;
  highlightText?: string;
  className?: string;
}

function escapeRegExp(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function Highlighted({ text, query }: { text: string; query: string }) {
  if (!query || query.length < 2) return <>{text}</>;
  const regex = new RegExp(`(${escapeRegExp(query)})`, "gi");
  const parts = text.split(regex);
  return (
    <>
      {parts.map((part, i) =>
        regex.test(part) ? (
          <strong key={i} className="font-semibold text-foreground">
            {part}
          </strong>
        ) : (
          part
        ),
      )}
    </>
  );
}

function formatDuration(minutes: number | null | undefined): string | null {
  if (minutes == null) return null;
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round((minutes / 60) * 10) / 10;
  return `${hours} h`;
}

function formatLastAccessed(value: string | null | undefined): string | null {
  if (!value) return null;
  const ts = new Date(value);
  if (Number.isNaN(ts.getTime())) return null;
  return ts.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function CourseCard({
  course,
  variant = "browse",
  progress,
  lastAccessedAt,
  highlightText = "",
  className,
}: CourseCardProps) {
  const duration = formatDuration(course.estimatedDurationMinutes);
  const moduleCount = course.moduleCount ?? null;
  const isEnrolledVariant = variant === "enrolled";
  const progressValue = Math.max(
    0,
    Math.min(100, progress ?? course.enrollmentProgress ?? 0),
  );
  const lastAccessedLabel = formatLastAccessed(lastAccessedAt);

  return (
    <Link
      href={`/courses/${course.id}`}
      aria-label={`Open course: ${course.title}`}
      className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 rounded-xl"
    >
      <Card
        role="article"
        aria-label={course.title}
        className={cn(
          "h-full bg-surface border-border shadow-sm transition-shadow",
          "hover:shadow-md cursor-pointer",
          "dark:bg-surface dark:border-border",
          className,
        )}
      >
        <CardHeader className="space-y-2">
          <CardTitle className="text-xl text-foreground">
            <Highlighted text={course.title} query={highlightText} />
          </CardTitle>
          {course.description ? (
            <CardDescription className="line-clamp-3 text-base text-muted-foreground">
              <Highlighted text={course.description} query={highlightText} />
            </CardDescription>
          ) : null}
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          {duration ? <span>{duration}</span> : null}
          {moduleCount != null ? (
            <span>
              {moduleCount} {moduleCount === 1 ? "module" : "modules"}
            </span>
          ) : null}
        </CardContent>
        {isEnrolledVariant ? (
          <CardFooter className="flex flex-col items-stretch gap-2 pt-0">
            <div
              role="progressbar"
              aria-valuenow={Math.round(progressValue)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`${Math.round(progressValue)}% complete`}
              className="h-1.5 w-full overflow-hidden rounded-full bg-border"
            >
              <div
                className="h-full bg-primary transition-[width]"
                style={{ width: `${progressValue}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{Math.round(progressValue)}% complete</span>
              {lastAccessedLabel ? <span>Last: {lastAccessedLabel}</span> : null}
            </div>
            <span className="text-sm font-medium text-primary">
              {progressValue > 0 ? "Continue" : "Start Learning"}
            </span>
          </CardFooter>
        ) : null}
      </Card>
    </Link>
  );
}
