"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";
import type { CourseOverview } from "@/types/analytics";

/** Root query-key namespace for analytics caches (reused for invalidation by 7.3/7.4). */
export const ANALYTICS_KEY = "analytics";

const STALE_5_MIN = 5 * 60 * 1000;

/**
 * Fetch the per-course analytics overview (Story 7.1 contract).
 *
 * Mirrors the `use-courses.ts` pattern: react-query + centralized `apiFetch`
 * (auth/refresh/error handling). Disabled until a `courseId` is available.
 */
export function useCourseOverview(courseId: string | undefined) {
  return useQuery<CourseOverview>({
    queryKey: [ANALYTICS_KEY, "overview", courseId],
    queryFn: () =>
      apiFetch<CourseOverview>(`/analytics/courses/${courseId}/overview`),
    enabled: Boolean(courseId),
    staleTime: STALE_5_MIN,
  });
}
