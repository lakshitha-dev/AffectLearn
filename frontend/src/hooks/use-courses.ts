"use client";

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiFetch } from "@/lib/api-client";
import type { CourseDetail, CourseListResponse } from "@/types/course";
import type {
  Enrollment,
  EnrollmentListResponse,
} from "@/types/enrollment";

interface UseCoursesParams {
  search?: string;
  page?: number;
  pageSize?: number;
}

const COURSES_KEY = "courses";
const ENROLLMENTS_KEY = "enrollments";

function buildCourseListQuery(params: UseCoursesParams): string {
  const search = new URLSearchParams();
  if (params.page) search.set("page", String(params.page));
  if (params.pageSize) search.set("page_size", String(params.pageSize));
  if (params.search && params.search.length >= 2) {
    search.set("search", params.search);
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

const STALE_5_MIN = 5 * 60 * 1000;

export function useCourses({ search, page = 1, pageSize = 20 }: UseCoursesParams = {}) {
  const trimmedSearch = search?.trim() ?? "";
  const effectiveSearch = trimmedSearch.length >= 2 ? trimmedSearch : "";
  return useQuery<CourseListResponse>({
    queryKey: [COURSES_KEY, { search: effectiveSearch, page, pageSize }],
    queryFn: () =>
      apiFetch<CourseListResponse>(
        `/courses${buildCourseListQuery({ search: effectiveSearch, page, pageSize })}`,
      ),
    placeholderData: keepPreviousData,
    staleTime: STALE_5_MIN,
  });
}

export function useCourse(courseId: string | undefined) {
  return useQuery<CourseDetail>({
    queryKey: [COURSES_KEY, courseId],
    queryFn: () => apiFetch<CourseDetail>(`/courses/${courseId}`),
    enabled: Boolean(courseId),
  });
}

export function useEnrollments(params: { page?: number; pageSize?: number } = {}) {
  const { page = 1, pageSize = 20 } = params;
  return useQuery<EnrollmentListResponse>({
    queryKey: [ENROLLMENTS_KEY, "list", { page, pageSize }],
    queryFn: () =>
      apiFetch<EnrollmentListResponse>(
        `/enrollments?page=${page}&page_size=${pageSize}`,
      ),
    staleTime: STALE_5_MIN,
  });
}

export function useEnrollmentStatus(courseId: string | undefined) {
  return useQuery<Enrollment | null>({
    queryKey: [ENROLLMENTS_KEY, "status", courseId],
    queryFn: () => apiFetch<Enrollment | null>(`/enrollments/${courseId}`),
    enabled: Boolean(courseId),
  });
}

export function useEnrollMutation() {
  const queryClient = useQueryClient();
  return useMutation<Enrollment, Error, { courseId: string }>({
    mutationFn: ({ courseId }) =>
      apiFetch<Enrollment>("/enrollments", {
        method: "POST",
        body: JSON.stringify({ courseId }),
      }),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: [ENROLLMENTS_KEY] });
      queryClient.invalidateQueries({ queryKey: [COURSES_KEY] });
      queryClient.setQueryData<CourseDetail | undefined>(
        [COURSES_KEY, variables.courseId],
        (prev) => (prev ? { ...prev, isEnrolled: true } : prev),
      );
    },
  });
}
