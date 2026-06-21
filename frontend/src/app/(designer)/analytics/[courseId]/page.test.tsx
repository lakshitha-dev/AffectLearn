/**
 * Tests for the per-course affect-heatmap page (Story 7.3, AC5 + page wiring).
 *
 * Covers: skeleton (role=status) with NO spinner while pending; the exact
 * empty-state copy for `sections: []`; the grid renders for data; the error path
 * shows an inline message + Retry. `useAffectHeatmap`, `useParams`, and
 * `next/link` are mocked.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { createElement } from "react";

import type { AffectHeatmapResponse } from "@/types/analytics";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
  }) => createElement("a", { href, ...rest }, children),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ courseId: "course-1" }),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/hooks/use-analytics", () => ({
  useAffectHeatmap: vi.fn(),
}));

import { useAffectHeatmap } from "@/hooks/use-analytics";
import CourseAffectHeatmapPage from "./page";

const mockUseAffectHeatmap = useAffectHeatmap as unknown as ReturnType<
  typeof vi.fn
>;

const response: AffectHeatmapResponse = {
  courseId: "course-1",
  sections: [
    {
      sectionId: "sec-1",
      sectionTitle: "Introduction",
      engagedPct: 70,
      confusedPct: 12,
      boredPct: 4,
      frustratedPct: 3,
      sampleCount: 90,
      confidence: "high",
      insufficientData: false,
    },
  ],
};

function result(over: Record<string, unknown> = {}) {
  return {
    data: response,
    isPending: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

describe("CourseAffectHeatmapPage", () => {
  beforeEach(() => {
    mockUseAffectHeatmap.mockReset();
  });

  it("shows a skeleton (role=status) and NO spinner while pending", () => {
    mockUseAffectHeatmap.mockReturnValue(
      result({ data: undefined, isPending: true }),
    );

    const { container } = render(<CourseAffectHeatmapPage />);

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(container.querySelector(".animate-spin")).toBeNull();
    expect(container.querySelector('[role="progressbar"]')).toBeNull();
  });

  it("renders the exact empty-state copy for sections: []", () => {
    mockUseAffectHeatmap.mockReturnValue(
      result({ data: { courseId: "course-1", sections: [] } }),
    );

    render(<CourseAffectHeatmapPage />);

    expect(
      screen.getByText(
        "No data yet — learners need to complete sessions before affect data appears",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("grid")).toBeNull();
  });

  it("renders the heatmap grid when data is present", () => {
    mockUseAffectHeatmap.mockReturnValue(result());

    render(<CourseAffectHeatmapPage />);

    expect(
      screen.getByRole("grid", { name: "Affect distribution by section" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Introduction")).toBeInTheDocument();
  });

  it("shows an inline error message + Retry on fetch error", () => {
    mockUseAffectHeatmap.mockReturnValue(
      result({ data: undefined, isError: true, error: new Error("boom") }),
    );

    render(<CourseAffectHeatmapPage />);

    const region = screen.getByText(
      "Couldn't load the affect heatmap",
    ).parentElement!;
    expect(within(region).getByRole("button", { name: /Retry/ })).toBeInTheDocument();
    expect(within(region).getByText("boom")).toBeInTheDocument();
  });
});
