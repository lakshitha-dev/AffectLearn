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
import {
  useAffectHeatmap,
  useCourseOverview,
  useSectionDetail,
} from "./use-analytics";

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

const HEATMAP = {
  courseId: "c1",
  sections: [
    {
      sectionId: "s1",
      sectionTitle: "Intro",
      engagedPct: 70,
      confusedPct: 10,
      boredPct: 5,
      frustratedPct: 2,
      sampleCount: 90,
      confidence: "high" as const,
      insufficientData: false,
    },
  ],
};

describe("useAffectHeatmap", () => {
  beforeEach(() => {
    mockApiFetch.mockReset();
    mockApiFetch.mockResolvedValue(HEATMAP);
  });

  it("calls apiFetch with the correct affect-heatmap URL", async () => {
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useAffectHeatmap("c1"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockApiFetch).toHaveBeenCalledTimes(1);
    expect(mockApiFetch).toHaveBeenCalledWith(
      "/analytics/courses/c1/affect-heatmap",
    );
    expect(result.current.data).toEqual(HEATMAP);
  });

  it("is disabled and does not fetch when courseId is undefined", async () => {
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useAffectHeatmap(undefined), {
      wrapper,
    });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiFetch).not.toHaveBeenCalled();
  });
});

const SECTION_DETAIL = {
  sectionId: "sec-1",
  sectionTitle: "Subnetting",
  affectDistribution: {
    engagedPct: 40,
    confusedPct: 68,
    boredPct: 10,
    frustratedPct: 12,
  },
  temporalDistribution: [{ binIndex: 0, confusedPct: 50 }],
  keyInsights: {
    mostTriggeredAdaptationType: "hint",
    averageConfusionDurationSeconds: 12,
  },
  content: [],
  sampleCount: 80,
  confidence: "high" as const,
  insufficientData: false,
};

describe("useSectionDetail", () => {
  beforeEach(() => {
    mockApiFetch.mockReset();
    mockApiFetch.mockResolvedValue(SECTION_DETAIL);
  });

  it("calls apiFetch with the correct section-detail URL", async () => {
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useSectionDetail("sec-1"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockApiFetch).toHaveBeenCalledTimes(1);
    expect(mockApiFetch).toHaveBeenCalledWith(
      "/analytics/sections/sec-1/detail",
    );
    expect(result.current.data).toEqual(SECTION_DETAIL);
  });

  it("is disabled and does not fetch when sectionId is undefined", async () => {
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useSectionDetail(undefined), {
      wrapper,
    });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mockApiFetch).not.toHaveBeenCalled();
  });
});
