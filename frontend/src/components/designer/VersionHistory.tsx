"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";

import { apiFetch } from "@/lib/api-client";

interface VersionSummary {
  id: string;
  versionNumber: number;
  publishedAt: string;
  publishedByName: string | null;
}

interface SnapshotModule {
  title?: string;
  lessons?: { title?: string; sections?: { title?: string }[] }[];
}

interface VersionDetail extends VersionSummary {
  snapshot: { title?: string; modules?: SnapshotModule[] };
}

/**
 * Published version history for a course.
 *
 * Every publish has captured the entire content tree into `content_versions` since migration 025,
 * and until now nothing could read one back: the snapshots accumulated where no screen and no
 * endpoint could reach them. A designer had no way to see that a previous version existed, when
 * it went out, or what it contained.
 *
 * Read-only. Restoring a version would rewrite live content that learners' progress rows point
 * at, and `section_progress.content_version_id` records which version a learner actually saw —
 * so a restore is a research-data question, not a button. Seeing what was published is the part
 * that was missing, and it is the part that is safe.
 */
export function VersionHistory({ courseId }: { courseId: string }) {
  const [openId, setOpenId] = useState<string | null>(null);

  const listQuery = useQuery<VersionSummary[]>({
    queryKey: ["courseVersions", courseId],
    queryFn: () => apiFetch<VersionSummary[]>(`/courses/${courseId}/versions`),
  });

  const detailQuery = useQuery<VersionDetail>({
    queryKey: ["courseVersion", openId],
    queryFn: () => apiFetch<VersionDetail>(`/courses/versions/${openId}`),
    enabled: Boolean(openId),
  });

  const versions = listQuery.data ?? [];

  return (
    <section className="mt-10 rounded-lg border border-border bg-surface p-6">
      <h2 className="font-semibold text-foreground">Published versions</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        A snapshot of the whole course is captured every time it is published.
      </p>

      {listQuery.isPending ? (
        <p className="mt-4 text-sm text-muted-foreground">Loading history…</p>
      ) : listQuery.isError ? (
        <p className="mt-4 text-sm text-muted-foreground">
          Could not load the version history.
        </p>
      ) : versions.length === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          Nothing published yet. The first snapshot is taken when you publish this course.
        </p>
      ) : (
        <ul className="mt-4 divide-y divide-border">
          {versions.map((version) => {
            const open = openId === version.id;
            return (
              <li key={version.id} className="py-3">
                <button
                  type="button"
                  onClick={() => setOpenId(open ? null : version.id)}
                  aria-expanded={open}
                  className="flex w-full items-center gap-2 text-left"
                >
                  {open ? (
                    <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                  <span className="font-medium text-foreground">
                    Version {version.versionNumber}
                  </span>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {new Date(version.publishedAt).toLocaleString()}
                    {version.publishedByName ? ` · ${version.publishedByName}` : ""}
                  </span>
                </button>

                {open && (
                  <div className="mt-3 pl-6">
                    {detailQuery.isPending ? (
                      <p className="text-sm text-muted-foreground">Loading snapshot…</p>
                    ) : detailQuery.isError || !detailQuery.data ? (
                      <p className="text-sm text-muted-foreground">
                        Could not load this snapshot.
                      </p>
                    ) : (
                      <ol className="space-y-2 text-sm">
                        {(detailQuery.data.snapshot.modules ?? []).map((mod, mi) => (
                          <li key={mi}>
                            <p className="font-medium text-foreground">
                              {mi + 1}. {mod.title ?? "Untitled module"}
                            </p>
                            <ul className="mt-1 space-y-0.5 pl-4 text-muted-foreground">
                              {(mod.lessons ?? []).map((lesson, li) => (
                                <li key={li}>
                                  {lesson.title ?? "Untitled lesson"}
                                  <span className="ml-2 text-xs">
                                    ({lesson.sections?.length ?? 0}{" "}
                                    {(lesson.sections?.length ?? 0) === 1
                                      ? "section"
                                      : "sections"}
                                    )
                                  </span>
                                </li>
                              ))}
                            </ul>
                          </li>
                        ))}
                        {(detailQuery.data.snapshot.modules ?? []).length === 0 && (
                          <li className="text-muted-foreground">
                            This version had no modules.
                          </li>
                        )}
                      </ol>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
