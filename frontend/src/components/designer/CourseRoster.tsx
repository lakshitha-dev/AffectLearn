"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";

interface RosterEntry {
  userId: string;
  firstName: string;
  lastName: string;
  emailAddress: string;
  enrolledAt: string;
  lastAccessedAt: string | null;
  status: string;
  completedSections: number;
  totalSections: number;
}

/**
 * Who is enrolled on this course, and how far they have got.
 *
 * A designer had no way to see this. The only learner aggregate that existed spans every course a
 * learner is enrolled in, so it could not be shown to a course's author without leaking other
 * designers' data; this one is course-scoped.
 *
 * No affect data here on purpose. "Who is on my course and how far along are they" is a roster
 * question; how any individual learner appeared to the detector is a research question, and the
 * analytics screens answer it in aggregate rather than per named person.
 */
export function CourseRoster({ courseId }: { courseId: string }) {
  const { data, isPending, isError } = useQuery<RosterEntry[]>({
    queryKey: ["courseRoster", courseId],
    queryFn: () => apiFetch<RosterEntry[]>(`/learners/courses/${courseId}/roster`),
  });

  const roster = data ?? [];

  return (
    <section className="mt-10 rounded-lg border border-border bg-surface p-6">
      <h2 className="font-semibold text-foreground">Enrolled learners</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Progress is counted over this course&apos;s sections only.
      </p>

      {isPending ? (
        <p className="mt-4 text-sm text-muted-foreground">Loading roster…</p>
      ) : isError ? (
        <p className="mt-4 text-sm text-muted-foreground">Could not load the roster.</p>
      ) : roster.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          Nobody has enrolled on this course yet.
        </p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="py-2 pr-4 font-medium text-muted-foreground">Learner</th>
                <th className="py-2 pr-4 font-medium text-muted-foreground">Progress</th>
                <th className="py-2 pr-4 font-medium text-muted-foreground">Last active</th>
                <th className="py-2 font-medium text-muted-foreground">Status</th>
              </tr>
            </thead>
            <tbody>
              {roster.map((entry) => {
                const pct =
                  entry.totalSections > 0
                    ? Math.round((entry.completedSections / entry.totalSections) * 100)
                    : 0;
                return (
                  <tr key={entry.userId} className="border-b border-border/60">
                    <td className="py-2 pr-4">
                      <span className="text-foreground">
                        {entry.firstName} {entry.lastName}
                      </span>
                      <span className="block text-xs text-muted-foreground">
                        {entry.emailAddress}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-muted-foreground">
                      {entry.completedSections}/{entry.totalSections}
                      <span className="ml-2 text-xs">({pct}%)</span>
                    </td>
                    <td className="py-2 pr-4 text-muted-foreground">
                      {entry.lastAccessedAt
                        ? new Date(entry.lastAccessedAt).toLocaleDateString()
                        : "Not started"}
                    </td>
                    <td className="py-2">
                      <span
                        className={
                          entry.status === "dropped"
                            ? "rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                            : "rounded-full bg-success/10 px-2 py-0.5 text-xs text-success"
                        }
                      >
                        {entry.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
