/**
 * Tests for the analytics data layer (Story 7.2, AC5).
 *
 * Verifies `useCourseOverview` builds the correct overview URL via the shared
 * `apiFetch`, and is disabled (no fetch) when `courseId` is undefined.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";

vi.mock("@/lib/api-client", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api-client";
import { useCourseOverview } from "./use-analytics";

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>;

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

const OVERVIEW = {
  courseId: "c1",
  totalLearners: 10,
  completionRate: 50,
  averageEngagementScore: 72,
  confusionHotspotCount: 2,
  sampleCount: 120,
  confidence: "high" as const,
  insufficientData: false,
};

describe("useCourseOverview", () => {
  beforeEach(() => {
    mockApiFetch.mockReset();
    mockApiFetch.mockResolvedValue(OVERVIEW);
  });

  it("calls apiFetch with the correct per-course overview URL", async () => {
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useCourseOverview("c1"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockApiFetch).toHaveBeenCalledTimes(1);
    expect(mockApiFetch).toHaveBeenCalledWith("/analytics/courses/c1/overview");
    expect(result.current.data).toEqual(OVERVIEW);
  });

  it("is disabled and does not fetch when courseId is undefined", async () => {
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useCourseOverview(undefined), {
      wrapper,
    });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiFetch).not.toHaveBeenCalled();
  });
});
