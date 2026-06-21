"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";
import type {
  AffectHeatmapResponse,
  CourseOverview,
  SectionDetailResponse,
} from "@/types/analytics";

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

/**
 * Fetch the per-section detail (Story 7.1 contract → Story 7.4 consumer).
 *
 * Mirrors {@link useCourseOverview}/{@link useAffectHeatmap} exactly: react-query
 * + centralized `apiFetch`, cached under {@link ANALYTICS_KEY}, 5-min stale time,
 * disabled until a `sectionId` is available. The detail endpoint is section-keyed
 * (no courseId in the path).
 */
export function useSectionDetail(sectionId: string | undefined) {
  return useQuery<SectionDetailResponse>({
    queryKey: [ANALYTICS_KEY, "section-detail", sectionId],
    queryFn: () =>
      apiFetch<SectionDetailResponse>(
        `/analytics/sections/${sectionId}/detail`,
      ),
    enabled: Boolean(sectionId),
    staleTime: STALE_5_MIN,
  });
}

/**
 * Fetch the per-course affect heatmap (Story 7.1 contract → Story 7.3 consumer).
 *
 * Mirrors {@link useCourseOverview} exactly: react-query + centralized
 * `apiFetch`, cached under {@link ANALYTICS_KEY}, 5-min stale time, disabled
 * until a `courseId` is available. Sections arrive already course-ordered.
 */
export function useAffectHeatmap(courseId: string | undefined) {
  return useQuery<AffectHeatmapResponse>({
    queryKey: [ANALYTICS_KEY, "heatmap", courseId],
    queryFn: () =>
      apiFetch<AffectHeatmapResponse>(
        `/analytics/courses/${courseId}/affect-heatmap`,
      ),
    enabled: Boolean(courseId),
    staleTime: STALE_5_MIN,
  });
}
